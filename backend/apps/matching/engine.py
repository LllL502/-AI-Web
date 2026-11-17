"""可解释、缺失感知的 TF-IDF 六因子匹配引擎。

本模块刻意保持与 Django ORM 解耦：视图层把已通过审核的可检索字段以及
脱敏后的地点层级转换为 ``ItemFeature``。私密答案、联系方式、会话和认领标签
不会因为序列化疏忽进入词表或解释结果；匹配解释也只输出分数，
不输出受保护地点名称。
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping, Sequence

import jieba
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

FACTOR_ORDER = ("text", "category", "location", "time", "color", "brand")
DEFAULT_WEIGHTS = {
    "text": 0.50,
    "category": 0.15,
    "location": 0.12,
    "time": 0.10,
    "color": 0.08,
    "brand": 0.05,
}

# 用户只需按主观可能性排序，不被迫填写伪精确概率。
# 该衰减系数使“第 1 可能地点”精确命中保留 1.0，其他候选仍提供渐弱证据。
LOCATION_RANK_CONFIDENCE = (1.0, 0.8, 0.65, 0.5, 0.4)


@dataclass(frozen=True)
class ItemFeature:
    """算法可见的最小特征快照；不提供私密原文或联系方式入口。"""

    id: str
    kind: str
    public_text: str
    owner_id: str | None = None
    category_path: tuple[str, ...] = ()
    location_path: tuple[str, ...] = ()
    location_hypotheses: tuple[tuple[tuple[str, ...], float], ...] = ()
    location_points: tuple[tuple[float, float, float], ...] = ()
    color_values: tuple[str, ...] = ()
    brand: str | None = None
    event_start: datetime | None = None
    event_end: datetime | None = None
    review_status: str = "APPROVED"
    business_status: str = "OPEN"
    source_revision: int = 1
    current_available: bool = True


@dataclass(frozen=True)
class FactorValue:
    score: float
    available: bool
    conflict: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class RankedCandidate:
    candidate_id: str
    score: float
    coverage: float
    factor_scores: Mapping[str, float | None]
    effective_weights: Mapping[str, float]
    contributions: Mapping[str, float]
    missing_factors: tuple[str, ...]
    conflicts: tuple[str, ...]
    actionable: bool
    source_revision: int
    text_terms: tuple[tuple[str, float], ...] = ()
    current_available: bool = True


@dataclass
class FittedIndex:
    status: str
    vectorizer: TfidfVectorizer | None
    matrix: sparse.csr_matrix
    documents: tuple[ItemFeature, ...]
    id_to_row: dict[str, int]
    inverted_index: dict[str, tuple[str, ...]]
    exclusion_counts: dict[str, int] = field(default_factory=dict)


class ChinesePreprocessor:
    """执行可复现的 Unicode、别称、停用词和中文分词处理。"""

    _punctuation = re.compile(r"[^\w\u4e00-\u9fff+#.\-]+", re.UNICODE)

    def __init__(
        self,
        aliases: Mapping[str, str] | None = None,
        stop_words: Iterable[str] | None = None,
        dictionary_version: str = "campus-dict-v1",
        custom_words: Iterable[str] | None = None,
    ) -> None:
        self.aliases = {self.normalize_text(k): self.normalize_text(v) for k, v in (aliases or {}).items()}
        # 否定词明确从停用词中排除，避免“有挂绳”和“无挂绳”被处理成同义描述。
        negations = {"不", "没有", "无", "未", "不是"}
        self.stop_words = set(stop_words or ()) - negations
        self.dictionary_version = dictionary_version
        for word in custom_words or ():
            jieba.add_word(word)

    @classmethod
    def normalize_text(cls, text: str | None) -> str:
        normalized = unicodedata.normalize("NFKC", text or "").lower().strip()
        normalized = cls._punctuation.sub(" ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    def tokenize(self, text: str) -> list[str]:
        normalized = self.normalize_text(text)
        if not normalized:
            return []
        # 先按较长别称替换，避免“校图”与“图书馆”等地点称谓落入不同维度。
        for alias in sorted(self.aliases, key=len, reverse=True):
            normalized = normalized.replace(alias, self.aliases[alias])
        return [token.strip() for token in jieba.lcut(normalized) if token.strip() and token not in self.stop_words]

    def preprocess(self, text: str) -> dict[str, object]:
        normalized = self.normalize_text(text)
        tokens = self.tokenize(normalized)
        return {
            "original": text,
            "normalized": normalized,
            "tokens": tokens,
            "dictionary_version": self.dictionary_version,
        }


class MatchingEngine:
    """八段职责完整的主匹配引擎。"""

    def __init__(
        self,
        preprocessor: ChinesePreprocessor | None = None,
        weights: Mapping[str, float] | None = None,
        min_coverage: float = 0.60,
        min_score: float = 0.35,
        time_tau_days: float = 7.0,
        time_tolerance_hours: float = 6.0,
    ) -> None:
        self.preprocessor = preprocessor or ChinesePreprocessor()
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        self.min_coverage = float(min_coverage)
        self.min_score = float(min_score)
        self.time_tau_days = float(time_tau_days)
        self.time_tolerance_hours = float(time_tolerance_hours)
        self._validate_config()

    def _validate_config(self) -> None:
        if set(self.weights) != set(FACTOR_ORDER):
            raise ValueError("六因子权重必须完整且不能包含未知因子")
        if any(not math.isfinite(value) or value < 0 for value in self.weights.values()):
            raise ValueError("权重必须是非负有限数")
        if not math.isclose(sum(self.weights.values()), 1.0, abs_tol=1e-9):
            raise ValueError("六因子权重之和必须为 1")
        if not 0 <= self.min_coverage <= 1:
            raise ValueError("证据覆盖阈值必须位于 [0,1]")
        if not 0 <= self.min_score <= 1:
            raise ValueError("候选最低分数必须位于 [0,1]")
        if self.time_tau_days <= 0:
            raise ValueError("时间衰减 tau 必须大于 0")

    # 1/8：中文预处理。
    def preprocess(self, text: str) -> dict[str, object]:
        return self.preprocessor.preprocess(text)

    # 2/8：一次拟合整个候选公开语料，并生成真实词项倒排表。
    def fit_index(self, documents: Sequence[ItemFeature]) -> FittedIndex:
        eligible, exclusion_counts = self.generate_candidates(None, documents)
        texts = [document.public_text for document in eligible]
        if not texts or not any(self.preprocessor.tokenize(text) for text in texts):
            return FittedIndex(
                status="EMPTY",
                vectorizer=None,
                matrix=sparse.csr_matrix((len(eligible), 0)),
                documents=tuple(eligible),
                id_to_row={document.id: row for row, document in enumerate(eligible)},
                inverted_index={},
                exclusion_counts=exclusion_counts,
            )

        vectorizer = TfidfVectorizer(
            tokenizer=self.preprocessor.tokenize,
            token_pattern=None,
            lowercase=False,
            smooth_idf=True,
            sublinear_tf=True,
            norm="l2",
            dtype=np.float64,
        )
        matrix = vectorizer.fit_transform(texts).tocsr()
        terms = vectorizer.get_feature_names_out()
        inverted: dict[str, list[str]] = defaultdict(list)
        binary = matrix.copy()
        binary.data = np.ones_like(binary.data)
        for row, document in enumerate(eligible):
            for column in binary[row].indices:
                inverted[str(terms[column])].append(document.id)
        return FittedIndex(
            status="READY",
            vectorizer=vectorizer,
            matrix=matrix,
            documents=tuple(eligible),
            id_to_row={document.id: row for row, document in enumerate(eligible)},
            inverted_index={term: tuple(ids) for term, ids in inverted.items()},
            exclusion_counts=exclusion_counts,
        )

    # 3/8：查询必须使用候选索引的同一词表与 IDF，不允许重新 fit。
    def transform_query(self, query: ItemFeature, index: FittedIndex) -> sparse.csr_matrix:
        if index.status != "READY" or index.vectorizer is None:
            return sparse.csr_matrix((1, index.matrix.shape[1]))
        return index.vectorizer.transform([query.public_text]).tocsr()

    # 4/8：候选资格过滤与原因计数，与最终评分保持分离。
    def generate_candidates(
        self, query: ItemFeature | None, documents: Sequence[ItemFeature]
    ) -> tuple[list[ItemFeature], dict[str, int]]:
        candidates: list[ItemFeature] = []
        excluded: Counter[str] = Counter()
        for document in documents:
            if document.review_status != "APPROVED":
                excluded["not_approved"] += 1
            elif document.business_status != "OPEN" or not document.current_available:
                excluded["not_available"] += 1
            elif query is not None and document.id == query.id:
                excluded["same_item"] += 1
            elif query is not None and document.kind == query.kind:
                excluded["same_kind"] += 1
            elif query is not None and query.owner_id and document.owner_id == query.owner_id:
                excluded["same_owner"] += 1
            elif query is not None and not self._same_leaf_category(query, document):
                excluded["category_mismatch"] += 1
            elif query is not None and not self._time_is_feasible(query, document):
                excluded["time_conflict"] += 1
            else:
                candidates.append(document)
        return candidates, dict(sorted(excluded.items()))

    # 5/8：计算文本、类别、地点、时间、颜色与品牌六个独立因子。
    def compute_factors(
        self,
        query: ItemFeature,
        candidate: ItemFeature,
        text_similarity: float,
        text_available: bool,
    ) -> dict[str, FactorValue]:
        return {
            "text": FactorValue(float(np.clip(text_similarity, 0, 1)), text_available, detail="TF-IDF 余弦相似度"),
            "category": self._hierarchy_factor(query.category_path, candidate.category_path, "类别"),
            "location": self._uncertain_location_factor(query, candidate),
            "time": self._time_factor(query, candidate),
            "color": self._set_factor(query.color_values, candidate.color_values, "颜色"),
            "brand": self._brand_factor(query.brand, candidate.brand),
        }

    # 6/8：缺失感知归一化、证据门槛与稳定排序。
    def rank(self, query: ItemFeature, index: FittedIndex, top_k: int = 20) -> list[RankedCandidate]:
        if index.status != "READY" or index.vectorizer is None:
            return []
        eligible_ids = {item.id for item in self.generate_candidates(query, index.documents)[0]}
        query_vector = self.transform_query(query, index)
        query_nonzero = query_vector.nnz > 0
        similarities = (index.matrix @ query_vector.T).toarray().ravel() if query_nonzero else np.zeros(len(index.documents))
        ranked: list[RankedCandidate] = []
        for row, candidate in enumerate(index.documents):
            if candidate.id not in eligible_ids:
                continue
            candidate_nonzero = index.matrix[row].nnz > 0
            text_available = query_nonzero and candidate_nonzero
            factors = self.compute_factors(query, candidate, float(similarities[row]), text_available)
            coverage = sum(self.weights[name] for name, value in factors.items() if value.available)
            weighted_total = sum(
                self.weights[name] * value.score for name, value in factors.items() if value.available
            )
            normalized = weighted_total / coverage if coverage > 0 else 0.0
            effective = {
                name: (self.weights[name] / coverage if value.available and coverage else 0.0)
                for name, value in factors.items()
            }
            contributions = {
                name: effective[name] * value.score if value.available else 0.0 for name, value in factors.items()
            }
            missing = tuple(name for name, value in factors.items() if not value.available)
            conflicts = tuple(value.conflict for value in factors.values() if value.conflict)
            actionable = text_available and coverage >= self.min_coverage and candidate.current_available
            # top_k 只是上限，不是必须凑满的配额。
            if not actionable or normalized < self.min_score:
                continue
            terms = self._term_contributions(query_vector, index.matrix[row], index.vectorizer)
            ranked.append(
                RankedCandidate(
                    candidate_id=candidate.id,
                    score=normalized,
                    coverage=coverage,
                    factor_scores={name: value.score if value.available else None for name, value in factors.items()},
                    effective_weights=effective,
                    contributions=contributions,
                    missing_factors=missing,
                    conflicts=conflicts,
                    actionable=True,
                    source_revision=query.source_revision,
                    text_terms=terms,
                    current_available=candidate.current_available,
                )
            )
        ranked.sort(key=lambda result: (-int(result.actionable), -result.score, -result.coverage, result.candidate_id))
        return ranked[: max(0, top_k)]

    def _same_leaf_category(self, left: ItemFeature, right: ItemFeature) -> bool:
        """叶子类别必须相同，“钥匙”不会再与“水杯”互相候选。"""

        if not left.category_path or not right.category_path:
            return False
        return self.preprocessor.normalize_text(left.category_path[-1]) == self.preprocessor.normalize_text(
            right.category_path[-1]
        )

    @staticmethod
    def _time_is_feasible(left: ItemFeature, right: ItemFeature) -> bool:
        """拾获时间不得早于遗失时间；时间缺失时交给缺失感知评分。"""

        lost, found = (left, right) if left.kind == "LOST" else (right, left)
        if lost.kind != "LOST" or found.kind != "FOUND":
            return False
        if not lost.event_start or not found.event_start:
            return True
        return found.event_start >= lost.event_start

    # 7/8：生成同一评分快照的解释字段；不使用“概率”或“已证明”等措辞。
    def explain(
        self,
        result: RankedCandidate,
        model_version: str,
        index_version: str,
        computed_at: datetime,
    ) -> dict[str, object]:
        if not result.actionable:
            level = "信息不足，仅供浏览"
        elif result.score >= 0.80:
            level = "优先核查"
        elif result.score >= 0.60:
            level = "值得对照"
        else:
            level = "弱线索"
        return {
            "candidate_id": result.candidate_id,
            "score": round(result.score * 100, 2),
            "coverage": round(result.coverage, 6),
            "factor_scores": result.factor_scores,
            "effective_weights": result.effective_weights,
            "contributions": result.contributions,
            "missing_factors": list(result.missing_factors),
            "conflicts": list(result.conflicts),
            "text_terms": [{"term": term, "contribution": contribution} for term, contribution in result.text_terms],
            "level": level,
            "actionable": result.actionable,
            "current_available": result.current_available,
            "model_version": model_version,
            "dictionary_version": self.preprocessor.dictionary_version,
            "index_version": index_version,
            "source_revision": result.source_revision,
            "computed_at": computed_at.isoformat(),
        }

    # 8/8：以显式相关集合评估排名，供基准模型与消融实验共用。
    def evaluate(
        self, ranked_ids: Sequence[str], relevant_ids: set[str], k_values: Sequence[int] = (1, 3, 5, 10)
    ) -> dict[str, float]:
        metrics: dict[str, float] = {}
        for k in k_values:
            retrieved = list(ranked_ids[:k])
            hits = sum(item_id in relevant_ids for item_id in retrieved)
            metrics[f"precision@{k}"] = hits / len(retrieved) if retrieved else 0.0
            metrics[f"recall@{k}"] = hits / len(relevant_ids) if relevant_ids else 0.0
            metrics[f"hit@{k}"] = float(hits > 0)
        reciprocal_rank = next((1 / rank for rank, item_id in enumerate(ranked_ids, 1) if item_id in relevant_ids), 0.0)
        metrics["mrr"] = reciprocal_rank
        return metrics

    def _hierarchy_factor(self, left: tuple[str, ...], right: tuple[str, ...], label: str) -> FactorValue:
        if not left or not right:
            return FactorValue(0.0, False, detail=f"{label}未知")
        common_depth = 0
        for left_node, right_node in zip(left, right):
            if self.preprocessor.normalize_text(left_node) != self.preprocessor.normalize_text(right_node):
                break
            common_depth += 1
        if left == right:
            return FactorValue(1.0, True, detail=f"同一{label}")
        if common_depth:
            return FactorValue(0.65, True, detail=f"同一上级{label}")
        return FactorValue(0.0, True, conflict=f"{label}已知不同", detail=f"不同{label}层级")

    def _uncertain_location_factor(self, left: ItemFeature, right: ItemFeature) -> FactorValue:
        """对多个可能地点做置信度衰减后的最优对齐。

        遗失者可以完全不填候选地点；此时地点因子标记为缺失，
        由总分公式对其他已知因子重新归一化，不会被错误计成 0 分。
        """
        left_options = left.location_hypotheses or (
            ((left.location_path, 1.0),) if left.location_path else ()
        )
        right_options = right.location_hypotheses or (
            ((right.location_path, 1.0),) if right.location_path else ()
        )
        scores: list[tuple[float, str]] = []
        if left_options and right_options:
            for left_path, left_confidence in left_options:
                for right_path, right_confidence in right_options:
                    base = self._hierarchy_factor(left_path, right_path, "地点")
                    score = base.score * float(np.clip(left_confidence, 0, 1)) * float(
                        np.clip(right_confidence, 0, 1)
                    )
                    scores.append((score, base.detail or "地点层级比较"))

        # 真实地图采用 GCJ-02 坐标。250 米是校内步行尺度的平滑衰减参数；
        # 2 公里以外视为已知不同，避免跨校区远点仍贡献一个极小正分。
        if left.location_points and right.location_points:
            for left_lat, left_lng, left_confidence in left.location_points:
                for right_lat, right_lng, right_confidence in right.location_points:
                    lat1, lat2 = math.radians(left_lat), math.radians(right_lat)
                    delta_lat = math.radians(right_lat - left_lat)
                    delta_lng = math.radians(right_lng - left_lng)
                    haversine = (
                        math.sin(delta_lat / 2) ** 2
                        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
                    )
                    distance_m = 12_742_000 * math.asin(min(1.0, math.sqrt(haversine)))
                    base_score = math.exp(-distance_m / 250.0) if distance_m <= 2_000 else 0.0
                    score = base_score * float(np.clip(left_confidence, 0, 1)) * float(
                        np.clip(right_confidence, 0, 1)
                    )
                    scores.append((score, f"地图距离约 {round(distance_m):.0f} 米"))

        if not scores:
            return FactorValue(0.0, False, detail="地点未知，本因子不参与评分")

        best_score, best_detail = max(scores, key=lambda entry: entry[0])

        conflict = "候选地点均不同" if best_score == 0 else None
        return FactorValue(
            float(np.clip(best_score, 0, 1)),
            True,
            conflict=conflict,
            detail=f"{best_detail}（已按可能顺序衰减）",
        )

    def _set_factor(self, left: tuple[str, ...], right: tuple[str, ...], label: str) -> FactorValue:
        left_set = {self.preprocessor.normalize_text(value) for value in left if value}
        right_set = {self.preprocessor.normalize_text(value) for value in right if value}
        if not left_set or not right_set:
            return FactorValue(0.0, False, detail=f"{label}未知")
        score = len(left_set & right_set) / len(left_set | right_set)
        conflict = None if score else f"{label}已知不同"
        return FactorValue(score, True, conflict=conflict, detail="集合 Jaccard 相似度")

    def _brand_factor(self, left: str | None, right: str | None) -> FactorValue:
        if not left or not right:
            return FactorValue(0.0, False, detail="品牌未知")
        normalized_left = self.preprocessor.normalize_text(left)
        normalized_right = self.preprocessor.normalize_text(right)
        # 品牌只允许词典别称后的精确相同，不使用字符串近似猜测品牌。
        normalized_left = self.preprocessor.aliases.get(normalized_left, normalized_left)
        normalized_right = self.preprocessor.aliases.get(normalized_right, normalized_right)
        if normalized_left == normalized_right:
            return FactorValue(1.0, True, detail="品牌一致")
        return FactorValue(0.0, True, conflict="品牌已知不同", detail="品牌不一致")

    def _time_factor(self, query: ItemFeature, candidate: ItemFeature) -> FactorValue:
        if not query.event_start or not candidate.event_start:
            return FactorValue(0.0, False, detail="时间未知")
        lost, found = (query, candidate) if query.kind == "LOST" else (candidate, query)
        if lost.kind != "LOST" or found.kind != "FOUND":
            return FactorValue(0.0, False, detail="不是可比较的遗失/拾获时间")
        lost_end = lost.event_end or lost.event_start
        found_start = found.event_start
        tolerance_days = self.time_tolerance_hours / 24
        delta_days = (found_start - lost_end).total_seconds() / 86400
        if delta_days < -tolerance_days:
            return FactorValue(0.0, True, conflict="拾取时间早于遗失时间", detail="时间次序明确冲突")
        feasible_delta = max(delta_days, 0.0)
        return FactorValue(
            math.exp(-feasible_delta / self.time_tau_days),
            True,
            detail=f"事件间隔 {feasible_delta:.2f} 天，tau={self.time_tau_days:g} 天",
        )

    @staticmethod
    def _term_contributions(
        query_vector: sparse.csr_matrix,
        document_vector: sparse.csr_matrix,
        vectorizer: TfidfVectorizer,
        limit: int = 8,
    ) -> tuple[tuple[str, float], ...]:
        product = query_vector.multiply(document_vector).tocoo()
        if not product.nnz:
            return ()
        terms = vectorizer.get_feature_names_out()
        ranked = sorted(
            ((str(terms[column]), float(value)) for column, value in zip(product.col, product.data)),
            key=lambda item: (-item[1], item[0]),
        )
        return tuple(ranked[:limit])


def reference_tfidf(documents: Sequence[Sequence[str]]) -> tuple[list[str], np.ndarray]:
    """小规模独立参考实现，仅用于核验平滑 IDF、次线性 TF 与 L2 归一化。"""

    vocabulary = sorted({token for document in documents for token in document})
    document_frequency = {token: sum(token in set(document) for document in documents) for token in vocabulary}
    matrix = np.zeros((len(documents), len(vocabulary)), dtype=float)
    total_documents = len(documents)
    for row, document in enumerate(documents):
        counts = Counter(document)
        for column, token in enumerate(vocabulary):
            if counts[token]:
                tf = 1 + math.log(counts[token])
                idf = math.log((1 + total_documents) / (1 + document_frequency[token])) + 1
                matrix[row, column] = tf * idf
        norm = np.linalg.norm(matrix[row])
        if norm:
            matrix[row] /= norm
    return vocabulary, matrix
