from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.items.models import Item

from .engine import ChinesePreprocessor, ItemFeature, LOCATION_RANK_CONFIDENCE, MatchingEngine
from .models import AlgorithmConfig, IndexVersion, MatchCandidate, MatchRun


def _ancestor_names(instance) -> tuple[str, ...]:
    names: list[str] = []
    current = instance
    while current is not None:
        names.append(current.name)
        current = current.parent
    return tuple(reversed(names))


def item_to_feature(item: Item) -> ItemFeature:
    """映射算法的最小数据合同。

    地点只保留校内层级路径和排名衰减值，不读取自由文本精确地点、
    坐标、PrivateClue、联系方式或认领标签。
    """
    colors = tuple(value.strip() for value in item.color.replace("/", ",").split(",") if value.strip())
    candidates = list(item.location_candidates.all())
    location_hypotheses = tuple(
        (
            _ancestor_names(candidate.location),
            LOCATION_RANK_CONFIDENCE[min(candidate.rank, len(LOCATION_RANK_CONFIDENCE)) - 1],
        )
        for candidate in candidates
    )
    coordinate_candidates = list(item.coordinate_candidates.all())
    location_points = tuple(
        (
            float(candidate.latitude),
            float(candidate.longitude),
            LOCATION_RANK_CONFIDENCE[min(candidate.rank, len(LOCATION_RANK_CONFIDENCE)) - 1],
        )
        for candidate in coordinate_candidates
    )
    # 兼容升级前的旧单点记录；新发布流程以候选点表为准。
    if not location_points and item.latitude is not None and item.longitude is not None:
        location_points = ((float(item.latitude), float(item.longitude), 1.0),)
    # 兼容旧数据：旧记录如果直接指向校内子区域，仍作为已知地点。
    # 新流程的 Item.location 只指向公开校区根节点，不参与精确地点打分。
    legacy_location_path = _ancestor_names(item.location) if item.location.parent_id is not None else ()
    return ItemFeature(
        id=str(item.pk),
        kind=item.kind,
        public_text=item.searchable_text,
        owner_id=str(item.owner_id),
        category_path=_ancestor_names(item.category),
        location_path=legacy_location_path,
        location_hypotheses=location_hypotheses,
        location_points=location_points,
        color_values=colors,
        brand=item.brand or None,
        event_start=item.occurred_at,
        event_end=item.occurred_at,
        review_status=item.review_status,
        business_status=item.business_status,
        source_revision=item.published_revision or item.revisions.count() or 1,
        current_available=item.business_status in {Item.BusinessStatus.OPEN, Item.BusinessStatus.RESERVED},
    )


def _current_config() -> AlgorithmConfig:
    config = AlgorithmConfig.objects.filter(is_published=True).order_by("-published_at", "-id").first()
    if config is None:
        raise ValidationError("尚无已发布的算法配置")
    return config


@transaction.atomic
def execute_match_run(query_item: Item, actor) -> MatchRun:
    if query_item.owner_id != actor.id:
        raise PermissionDenied("只能为自己的遗失信息运行匹配")
    if query_item.kind != Item.Kind.LOST:
        raise ValidationError("当前版本只允许以遗失信息作为查询源")
    if query_item.review_status != Item.ReviewStatus.APPROVED:
        raise ValidationError("遗失信息需通过后端审核后才能发起匹配")

    config = _current_config()
    candidates = list(
        Item.objects.filter(
            kind=Item.Kind.FOUND,
            location__campus_id=query_item.location.campus_id,
            category_id=query_item.category_id,
            occurred_at__gte=query_item.occurred_at,
            review_status=Item.ReviewStatus.APPROVED,
            business_status__in=[Item.BusinessStatus.OPEN, Item.BusinessStatus.RESERVED],
        ).exclude(owner_id=query_item.owner_id).select_related("category__parent", "location__parent").prefetch_related(
            "location_candidates__location__parent", "coordinate_candidates"
        )
    )
    preprocessor = ChinesePreprocessor(
        aliases=config.preprocessing.get("aliases", {}),
        stop_words=config.preprocessing.get("stop_words", []),
        dictionary_version=config.preprocessing.get("dictionary_version", "campus-dict-v1"),
        custom_words=config.preprocessing.get("custom_words", []),
    )
    engine = MatchingEngine(
        preprocessor=preprocessor,
        weights=config.weights,
        min_coverage=config.thresholds.get("min_coverage", 0.60),
        min_score=config.thresholds.get("min_score", 0.35),
        time_tau_days=config.thresholds.get("time_tau_days", 7),
        time_tolerance_hours=config.thresholds.get("time_tolerance_hours", 6),
    )
    features = [item_to_feature(item) for item in candidates]
    index = engine.fit_index(features)
    corpus_payload = [{"id": feature.id, "revision": feature.source_revision} for feature in features]
    checksum = hashlib.sha256(json.dumps(corpus_payload, sort_keys=True).encode("utf-8")).hexdigest()
    index_record = IndexVersion.objects.create(
        version=f"idx-{timezone.now():%Y%m%d%H%M%S%f}",
        document_count=len(features),
        vocabulary_size=index.matrix.shape[1],
        artifact_path="runtime:in-memory-sparse-index",
        corpus_checksum=checksum,
        config=config,
        is_active=True,
    )
    IndexVersion.objects.filter(config=config, is_active=True).exclude(pk=index_record.pk).update(is_active=False)
    run = MatchRun.objects.create(
        query_item=query_item,
        requested_by=actor,
        config=config,
        index_version=index_record,
        status=MatchRun.Status.RUNNING,
        started_at=timezone.now(),
    )
    try:
        results = engine.rank(item_to_feature(query_item), index, top_k=50)
        now = timezone.now()
        MatchCandidate.objects.bulk_create(
            [
                MatchCandidate(
                    run=run,
                    candidate_item_id=result.candidate_id,
                    rank=rank,
                    raw_score=result.score,
                    coverage=result.coverage,
                    final_score=result.score,
                    factors={
                        "scores": result.factor_scores,
                        "effective_weights": result.effective_weights,
                        "contributions": result.contributions,
                    },
                    explanation=engine.explain(result, config.version, index_record.version, now),
                    is_actionable=result.actionable,
                )
                for rank, result in enumerate(results, 1)
            ]
        )
        run.status = MatchRun.Status.COMPLETED
        run.candidate_count = len(results)
        run.completed_at = now
        run.save(update_fields=["status", "candidate_count", "completed_at"])
    except Exception:
        run.status = MatchRun.Status.FAILED
        run.error_code = "matching_failed"
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "error_code", "completed_at"])
        raise
    return run
