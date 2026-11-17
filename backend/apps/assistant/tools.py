"""供 AI 工作流使用的最小权限工具集。

注册表中没有批准认领、删除物品或完成交接的工具。
所有读取工具都会在服务端重做校区与公开状态过滤。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import jieba
from django.db.models import Q

from apps.items.models import Item
from apps.items.serializers import ItemSerializer
from apps.stations.models import Station
from apps.stations.scope import selected_campus


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    read_only: bool
    input_schema: dict


TOOL_DEFINITIONS = (
    ToolDefinition(
        name="query_public_items",
        description="查询当前校区已公开且仍可认领的物品。",
        read_only=True,
        input_schema={"kind": "LOST|FOUND", "query": "string", "limit": "1..10"},
    ),
    ToolDefinition(
        name="read_public_item",
        description="读取一条真实公开物品的脱敏详情。",
        read_only=True,
        input_schema={"item_id": "uuid"},
    ),
    ToolDefinition(
        name="query_service_stations",
        description="查询当前校区已审批且开放的服务站。",
        read_only=True,
        input_schema={},
    ),
    ToolDefinition(
        name="generate_pending_draft",
        description="校验并生成待用户确认的发布草稿，不写入数据库。",
        read_only=True,
        input_schema={"item_payload": "validated item draft"},
    ),
)

STOP_WORDS = {"我", "的", "一个", "一只", "一串", "可能", "大概", "校园", "遗失", "丢失", "拾到", "捡到", "寻找"}


def public_items_queryset(request):
    return (
        Item.objects.filter(
            location__campus_id=selected_campus(request),
            review_status=Item.ReviewStatus.APPROVED,
            business_status=Item.BusinessStatus.OPEN,
        )
        .select_related("category", "location__campus__school", "station")
        .prefetch_related("media")
    )


def _search_tokens(value: str) -> list[str]:
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", " ", value).strip()
    tokens = []
    for token in jieba.lcut(normalized):
        token = token.strip()
        if len(token) < 2 or token in STOP_WORDS or token in tokens:
            continue
        tokens.append(token)
    return tokens[:8]


def _public_image_url(request, item: Item) -> str:
    assets = sorted(
        (asset for asset in item.media.all() if asset.is_public),
        key=lambda asset: (asset.sort_order, asset.pk),
    )
    if not assets:
        return ""
    image = assets[0].thumbnail or assets[0].file
    return request.build_absolute_uri(image.url + '?campus=' + str(item.location.campus_id)) if image else ""


def _public_item_record(request, item: Item, tokens: list[str] | None = None) -> dict:
    tokens = tokens or []
    searchable = item.searchable_text.lower()
    matched = [token for token in tokens if token.lower() in searchable]
    reasons = []
    if matched:
        reasons.append(f"公开描述命中：{'、'.join(matched[:4])}")
    reasons.append(f"公开类别：{item.category.name}")
    reasons.append(f"公开地点：{item.location.name}")
    image_url = _public_image_url(request, item)
    return {
        "id": str(item.pk),
        "is_demo": item.is_demo,
        "image_note": ("同类实物参考照片（演示），非该失物现场实拍" if '/demo-reference/' in image_url else "合成演示配图，不是该记录的实拍照片") if item.is_demo and image_url else "",
        "citation_id": f"item:{item.pk}",
        "kind": item.kind,
        "title": item.title,
        "description": item.description,
        "category": item.category.name,
        "brand": item.brand,
        "color": item.color,
        "occurred_at": item.occurred_at.isoformat(),
        "location": item.location.name,
        "image_url": image_url,
        "url": f"/items/{item.pk}",
        "reasons": reasons,
    }


def query_public_items(request, *, kind: str, query: str, limit: int = 5) -> list[dict]:
    if kind not in Item.Kind.values:
        return []
    limit = max(1, min(int(limit), 10))
    tokens = _search_tokens(query)
    queryset = public_items_queryset(request).filter(kind=kind)
    if tokens:
        predicate = Q()
        for token in tokens:
            predicate |= (
                Q(title__icontains=token)
                | Q(description__icontains=token)
                | Q(brand__icontains=token)
                | Q(color__icontains=token)
                | Q(category__name__icontains=token)
            )
        queryset = queryset.filter(predicate)
    else:
        return []
    return [
        _public_item_record(request, item, tokens)
        for item in queryset.order_by("-occurred_at", "-created_at")[:limit]
    ]


def read_public_item(request, *, item_id: str) -> dict | None:
    item = public_items_queryset(request).filter(pk=item_id).first()
    return _public_item_record(request, item) if item else None


def semantic_public_items(request, *, kind, query, limit=5, draft=None):
    from .local_models import embeddings, cosine
    from .providers import ProviderUnavailable
    from .vector_index import ensure_vectors, content_hash
    from .runtime import check_budget
    # No count cap: the live eligible corpus defines the index membership.
    eligible = public_items_queryset(request).filter(kind=kind)
    items = list(eligible.order_by("pk"))
    if not items:
        return []
    vectors = ensure_vectors(items, eligible)
    query_vector = embeddings([query])[0]
    if any(len(v) != len(query_vector) for v in vectors.values()):
        raise ProviderUnavailable("向量模型维度变化，请更新模型修订号并重建索引。")
    check_budget()
    ranked = sorted(((cosine(query_vector, vectors[item.pk]), item) for item in items if item.pk in vectors),
                    key=lambda pair: (-pair[0], str(pair[1].pk)))
    # A withdrawal/edit during inference must not return an old snapshot.
    recall = [(score, item) for score, item in ranked if score > 0][:50]
    live = {item.pk: item for item in eligible.filter(pk__in=[item.pk for _, item in recall])}
    ranked = [(score, live[item.pk]) for score, item in recall
              if item.pk in live and content_hash(live[item.pk]) == content_hash(item)]
    if draft is not None:
        from .ranking import rerank, accept_candidate, ACCEPTANCE_POLICY
        # Fixed recall pool independent of the requested display count.
        rows = rerank(draft, [(score, item) for score, item in ranked if score > 0][:50])
        rows = [row for row in rows if accept_candidate(row[3])]
        result = []
        for _, semantic, item, evidence in rows[:limit]:
            record = _public_item_record(request, item)
            record["semantic_similarity"] = round(semantic, 4)
            record["ranking"] = evidence
            record["ranking"]["acceptance_policy"] = ACCEPTANCE_POLICY
            record["reasons"] = evidence["explanations"] + record["reasons"]
            result.append(record)
        return result
    result = []
    for score, item in ranked[:limit]:
        if score <= 0:
            continue
        record = _public_item_record(request, item)
        record["semantic_similarity"] = round(score, 4)
        record["reasons"].insert(0, "本地向量语义相似度排序；不代表物品归属概率")
        result.append(record)
    return result


def query_service_stations(request) -> list[dict]:
    queryset = Station.objects.filter(
        location__campus_id=selected_campus(request),
        is_active=True,
        approval_status=Station.ApprovalStatus.APPROVED,
        status=Station.Status.OPEN,
    ).select_related("location")
    return [
        {
            "id": station.pk,
            "name": station.name,
            "address": station.address,
            "public_location": station.location.name,
        }
        for station in queryset.order_by("name")
    ]


def generate_pending_draft(request, *, item_payload: dict) -> dict:
    """只做业务校验，不调用 ``save`` 且不产生物品。"""
    serializer = ItemSerializer(data=item_payload, context={"request": request})
    serializer.is_valid(raise_exception=True)
    validated = serializer.validated_data
    category = validated["category"]
    location = validated["location"]
    station = validated.get("station")
    return {
        "persisted": False,
        "requires_user_confirmation": True,
        "payload": {
            "kind": validated["kind"],
            "title": validated["title"],
            "description": validated["description"],
            "category": category.pk,
            "category_name": category.name,
            "occurred_at": validated["occurred_at"].isoformat(),
            "location": location.pk,
            "location_name": location.name,
            "brand": validated.get("brand", ""),
            "color": validated.get("color", ""),
            "station": station.pk if station else None,
        },
    }

