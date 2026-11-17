"""多因子、可靠性自适应的线性加权匹配引擎。

与固定权重教学示例不同，本实现会判断颜色/品牌/地点等字段是否有值，
只在“有证据”的因子之间重新归一化权重，避免缺失字段被误判为不相似。
最终分数仍严格满足线性模型 S = Σ(w_i' × s_i)，且页面公开每个因子的
原始分数、有效权重和贡献值，满足竞赛评审的可复现与可解释要求。
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Iterable

from .similarity import cosine_similarity, top_term_contributions
from .text import normalize_text, tokenize
from .tfidf import TfidfVectorizer


DEFAULT_WEIGHTS = {
    "text": 0.56,
    "category": 0.14,
    "time": 0.12,
    "location": 0.12,
    "attributes": 0.06,
}

CATEGORY_GROUPS = [
    {"数码电子", "证件卡类"},
    {"箱包服饰", "生活用品"},
    {"书籍文具", "学习资料"},
]


def _read(item: Any, name: str, default: Any = "") -> Any:
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _item_text(item: Any) -> str:
    # 分类、地点有独立因子，此处避免把它们重复计权。
    return " ".join(str(_read(item, field)) for field in ("title", "description", "color", "brand"))


def _category_score(left: str, right: str) -> float:
    if left == right and left:
        return 1.0
    if any(left in group and right in group for group in CATEGORY_GROUPS):
        return 0.35
    return 0.0


def _time_score(left: str, right: str, half_life_days: float = 7.0) -> float:
    """指数时间衰减：相差一个半衰期后得分减半。"""
    try:
        delta = abs((datetime.fromisoformat(left) - datetime.fromisoformat(right)).total_seconds()) / 86400
        return math.exp(-math.log(2) * delta / half_life_days)
    except (TypeError, ValueError):
        return 0.0


def _token_overlap(left: str, right: str) -> float:
    left_norm, right_norm = normalize_text(left), normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if left_norm in right_norm or right_norm in left_norm:
        return 0.85
    left_tokens, right_tokens = set(tokenize(left_norm)), set(tokenize(right_norm))
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0.0


def _attribute_score(source: Any, candidate: Any) -> float:
    scores = []
    for field in ("color", "brand"):
        left, right = str(_read(source, field)), str(_read(candidate, field))
        if left and right:
            scores.append(_token_overlap(left, right))
    return sum(scores) / len(scores) if scores else 0.0


def _confidence(score: float, strong_signals: int) -> tuple[str, str]:
    if score >= 0.72 and strong_signals >= 3:
        return "high", "高度疑似同一物品，建议优先核验"
    if score >= 0.46 and strong_signals >= 2:
        return "medium", "存在多项共同特征，建议进一步确认"
    return "low", "线索有限，可作为扩展排查候选"


def rank_candidates(
    source: Any,
    candidates: Iterable[Any],
    weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """按融合分数从高到低返回候选及完整解释证据。"""
    candidates = list(candidates)
    if not candidates:
        return []
    base_weights = {**DEFAULT_WEIGHTS, **(weights or {})}

    documents = [_item_text(source), *[_item_text(item) for item in candidates]]
    vectors = TfidfVectorizer().fit_transform(documents)
    source_vector = vectors[0]
    results: list[dict[str, Any]] = []

    for candidate, candidate_vector in zip(candidates, vectors[1:]):
        factors = {
            "text": cosine_similarity(source_vector, candidate_vector),
            "category": _category_score(_read(source, "category"), _read(candidate, "category")),
            "time": _time_score(_read(source, "event_time"), _read(candidate, "event_time")),
            "location": _token_overlap(_read(source, "location"), _read(candidate, "location")),
            "attributes": _attribute_score(source, candidate),
        }
        availability = {
            "text": bool(_item_text(source).strip() and _item_text(candidate).strip()),
            "category": bool(_read(source, "category") and _read(candidate, "category")),
            "time": bool(_read(source, "event_time") and _read(candidate, "event_time")),
            "location": bool(_read(source, "location") and _read(candidate, "location")),
            "attributes": any(
                _read(source, field) and _read(candidate, field) for field in ("color", "brand")
            ),
        }
        active_total = sum(base_weights[name] for name, active in availability.items() if active)
        effective_weights = {
            name: (base_weights[name] / active_total if active and active_total else 0.0)
            for name, active in availability.items()
        }
        contributions = {name: factors[name] * effective_weights[name] for name in factors}
        final_score = sum(contributions.values())
        strong_signals = sum(value >= 0.65 for value in factors.values())
        confidence, recommendation = _confidence(final_score, strong_signals)
        results.append({
            "item": candidate,
            "score": round(final_score, 4),
            "score_percent": round(final_score * 100, 1),
            "confidence": confidence,
            "recommendation": recommendation,
            "factors": {name: round(value, 4) for name, value in factors.items()},
            "effective_weights": {name: round(value, 4) for name, value in effective_weights.items()},
            "contributions": {name: round(value, 4) for name, value in contributions.items()},
            "shared_terms": top_term_contributions(source_vector, candidate_vector),
        })

    return sorted(results, key=lambda result: result["score"], reverse=True)

