"""在固定合成基准上运行 B0–B3 与消融实验。

本命令只读取 BenchmarkPair 中的 synthetic 标注，认领、归还、消息和
私密线索均不作为训练标签。输出仅保存聚合指标与配置，不泄露配对 ID。
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.items.models import Item
from apps.matching.engine import ChinesePreprocessor, DEFAULT_WEIGHTS, ItemFeature, MatchingEngine
from apps.matching.models import AlgorithmConfig, BenchmarkPair
from apps.matching.services import item_to_feature


K_VALUES = (1, 3, 5, 10)
TUNING_CANDIDATES = {
    "balanced": DEFAULT_WEIGHTS,
    "text_heavy": {"text": 0.60, "category": 0.12, "location": 0.10, "time": 0.08, "color": 0.06, "brand": 0.04},
    "structure_heavy": {"text": 0.40, "category": 0.20, "location": 0.15, "time": 0.10, "color": 0.10, "brand": 0.05},
}


class Command(BaseCommand):
    help = "运行固定演示基准 B0–B3 与消融实验，生成可追溯 JSON 证据"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=str(Path(settings.BASE_DIR).parent / "artifacts" / "experiment-results" / "demo-benchmark.json"),
            help="输出 JSON 路径",
        )

    def handle(self, *args, **options):
        pairs = list(
            BenchmarkPair.objects.filter(is_synthetic=True, is_match=True)
            .select_related(
                "lost_item__category__parent", "lost_item__location__parent",
                "found_item__category__parent", "found_item__location__parent",
            )
            .order_by("split", "lost_item_id")
        )
        split_counts = {split: sum(pair.split == split for pair in pairs) for split in ("TRAIN", "VALIDATION", "TEST")}
        if split_counts != {"TRAIN": 60, "VALIDATION": 20, "TEST": 20}:
            raise CommandError(f"基准划分不符合 60/20/20 合同：{split_counts}")

        candidate_items = list(
            Item.objects.filter(
                is_demo=True,
                kind=Item.Kind.FOUND,
                review_status=Item.ReviewStatus.APPROVED,
                business_status__in=[Item.BusinessStatus.OPEN, Item.BusinessStatus.RESERVED],
            ).select_related("category__parent", "location__parent")
        )
        candidates = [item_to_feature(item) for item in candidate_items]
        config = AlgorithmConfig.objects.filter(is_published=True).order_by("-published_at", "-id").first()
        if config is None:
            raise CommandError("缺少已发布算法配置")

        processor = ChinesePreprocessor(
            aliases=config.preprocessing.get("aliases", {}),
            stop_words=config.preprocessing.get("stop_words", []),
            dictionary_version=config.preprocessing.get("dictionary_version", "campus-dict-v1"),
            custom_words=config.preprocessing.get("custom_words", []),
        )
        queries = {str(pair.lost_item_id): item_to_feature(pair.lost_item) for pair in pairs}
        relevant = {str(pair.lost_item_id): str(pair.found_item_id) for pair in pairs}
        by_split: dict[str, list[BenchmarkPair]] = defaultdict(list)
        for pair in pairs:
            by_split[pair.split].append(pair)

        # B3 只在 VALIDATION 上选权重；TEST 只在确定配置后评估一次。
        validation_scores = {}
        for name, weights in TUNING_CANDIDATES.items():
            engine = self._engine(processor, config, weights)
            rankings = self._engine_rankings(engine, candidates, queries, by_split["VALIDATION"])
            validation_scores[name] = self._aggregate(engine, rankings, relevant)["mrr"]
        selected_name = sorted(validation_scores, key=lambda name: (-validation_scores[name], name))[0]
        selected_weights = TUNING_CANDIDATES[selected_name]

        test_pairs = by_split["TEST"]
        methods = {}
        b0_engine = self._engine(processor, config, DEFAULT_WEIGHTS)
        methods["B0_token_jaccard"] = self._report(
            b0_engine, self._jaccard_rankings(processor, candidates, queries, test_pairs), relevant
        )
        methods["B1_tfidf_cosine"] = self._report(
            b0_engine, self._tfidf_rankings(b0_engine, candidates, queries, test_pairs), relevant
        )
        b2_engine = self._engine(processor, config, DEFAULT_WEIGHTS)
        methods["B2_six_factor_initial"] = self._report(
            b2_engine, self._engine_rankings(b2_engine, candidates, queries, test_pairs), relevant
        )
        b3_engine = self._engine(processor, config, selected_weights)
        methods["B3_validation_selected"] = self._report(
            b3_engine, self._engine_rankings(b3_engine, candidates, queries, test_pairs), relevant
        )

        ablations = {}
        for name, removed in {
            "without_location": {"location"},
            "without_time": {"time"},
            "text_only_without_structured": {"category", "location", "time", "color", "brand"},
        }.items():
            weights = self._remove_and_normalize(selected_weights, removed)
            engine = self._engine(processor, config, weights)
            ablations[name] = self._report(
                engine, self._engine_rankings(engine, candidates, queries, test_pairs), relevant
            )
        no_alias_processor = ChinesePreprocessor(
            stop_words=config.preprocessing.get("stop_words", []),
            dictionary_version="no-alias-ablation",
            custom_words=config.preprocessing.get("custom_words", []),
        )
        no_alias_engine = self._engine(no_alias_processor, config, selected_weights)
        ablations["without_aliases"] = self._report(
            no_alias_engine, self._engine_rankings(no_alias_engine, candidates, queries, test_pairs), relevant
        )

        eligible_ids = {feature.id for feature in candidates}
        eligibility_recall = mean(float(relevant[str(pair.lost_item_id)] in eligible_ids) for pair in test_pairs)
        payload = {
            "schema_version": 1,
            "evidence_kind": "synthetic_demo_benchmark",
            "model_version": config.version,
            "dictionary_version": processor.dictionary_version,
            "seed": 20261007,
            "demo_base_date": settings.DEMO_BASE_DATE,
            "split_counts": split_counts,
            "test_query_count": len(test_pairs),
            "candidate_count": len(candidates),
            "candidate_eligibility_recall": eligibility_recall,
            "selection": {
                "split": "VALIDATION",
                "criterion": "mrr",
                "scores": validation_scores,
                "selected": selected_name,
                "weights": selected_weights,
            },
            "methods": methods,
            "ablations": ablations,
            "limitations": [
                "基准为固定规则生成的合成数据，不代表真实校园准确率。",
                "每个查询只有一个显式正例，未标注候选不能视为真实负例。",
                "测试集仅在验证集选定配置后评估一次。",
            ],
        }
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"评测完成：{output}"))
        self.stdout.write(json.dumps({"selected": selected_name, "test": methods["B3_validation_selected"]}, ensure_ascii=False))

    @staticmethod
    def _engine(processor, config, weights):
        return MatchingEngine(
            preprocessor=processor,
            weights=weights,
            min_coverage=config.thresholds.get("min_coverage", 0.60),
            time_tau_days=config.thresholds.get("time_tau_days", 7),
            time_tolerance_hours=config.thresholds.get("time_tolerance_hours", 6),
        )

    @staticmethod
    def _engine_rankings(engine, candidates, queries, pairs):
        index = engine.fit_index(candidates)
        return {
            str(pair.lost_item_id): [result.candidate_id for result in engine.rank(queries[str(pair.lost_item_id)], index, top_k=len(candidates))]
            for pair in pairs
        }

    @staticmethod
    def _tfidf_rankings(engine, candidates, queries, pairs):
        index = engine.fit_index(candidates)
        rankings = {}
        for pair in pairs:
            query_id = str(pair.lost_item_id)
            vector = engine.transform_query(queries[query_id], index)
            similarities = (index.matrix @ vector.T).toarray().ravel() if vector.nnz else np.zeros(len(candidates))
            rankings[query_id] = [
                candidate_id for _, candidate_id in sorted(
                    ((float(similarities[row]), feature.id) for row, feature in enumerate(index.documents)),
                    key=lambda entry: (-entry[0], entry[1]),
                )
            ]
        return rankings

    @staticmethod
    def _jaccard_rankings(processor, candidates, queries, pairs):
        candidate_tokens = {feature.id: set(processor.tokenize(feature.public_text)) for feature in candidates}
        rankings = {}
        for pair in pairs:
            query_id = str(pair.lost_item_id)
            query_tokens = set(processor.tokenize(queries[query_id].public_text))
            scored = []
            for feature in candidates:
                union = query_tokens | candidate_tokens[feature.id]
                score = len(query_tokens & candidate_tokens[feature.id]) / len(union) if union else 0.0
                scored.append((score, feature.id))
            rankings[query_id] = [candidate_id for _, candidate_id in sorted(scored, key=lambda entry: (-entry[0], entry[1]))]
        return rankings

    @staticmethod
    def _aggregate(engine, rankings, relevant):
        per_query = [engine.evaluate(ranked, {relevant[query_id]}, K_VALUES) for query_id, ranked in rankings.items()]
        keys = [f"{metric}@{k}" for k in K_VALUES for metric in ("precision", "recall", "hit")] + ["mrr"]
        return {key: mean(row[key] for row in per_query) for key in keys}

    def _report(self, engine, rankings, relevant):
        metrics = self._aggregate(engine, rankings, relevant)
        per_query_mrr = [engine.evaluate(ranked, {relevant[query_id]}, K_VALUES)["mrr"] for query_id, ranked in rankings.items()]
        rng = random.Random(20261007)
        bootstrap = []
        for _ in range(2000):
            bootstrap.append(mean(rng.choice(per_query_mrr) for _ in per_query_mrr))
        low, high = np.percentile(bootstrap, [2.5, 97.5])
        return {
            "metrics": metrics,
            "mrr_bootstrap_95_ci": [float(low), float(high)],
            "query_count": len(rankings),
        }

    @staticmethod
    def _remove_and_normalize(weights, removed):
        retained_total = sum(value for name, value in weights.items() if name not in removed)
        return {name: (0.0 if name in removed else value / retained_total) for name, value in weights.items()}
