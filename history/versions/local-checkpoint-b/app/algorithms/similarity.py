"""余弦相似度与词项贡献度解释。"""

from __future__ import annotations


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    """计算两个已归一化稀疏向量的点积，结果截断至 [0, 1]。"""
    if not left or not right:
        return 0.0
    # 遍历更短向量可将时间复杂度降为 O(min(|A|, |B|))。
    short, long = (left, right) if len(left) <= len(right) else (right, left)
    score = sum(value * long.get(term, 0.0) for term, value in short.items())
    return max(0.0, min(1.0, score))


def top_term_contributions(
    left: dict[str, float], right: dict[str, float], limit: int = 4
) -> list[dict[str, float | str]]:
    """返回对余弦分数贡献最大的共享词，供页面解释“为什么匹配”。"""
    contributions = [
        {"term": term, "contribution": round(value * right.get(term, 0.0), 4)}
        for term, value in left.items()
        if term in right
    ]
    return sorted(contributions, key=lambda item: item["contribution"], reverse=True)[:limit]

