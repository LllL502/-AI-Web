"""从零实现的平滑 TF-IDF 向量器。

核心公式：
    tf(t, d)  = 1 + ln(count(t, d))               （次线性词频）
    idf(t)    = ln((1 + N) / (1 + df(t))) + 1    （平滑逆文档频率）
    v(t, d)   = tf(t, d) × idf(t)，最后进行 L2 归一化

平滑项可防止新语料下除零；次线性 TF 可抑制描述中重复词的异常放大。
稀疏字典表示只保存非零维度，便于后续扩展到更大的校园数据集。
"""

from __future__ import annotations

import math
from collections import Counter

from .text import tokenize


class TfidfVectorizer:
    """小型、透明、可序列化思路清晰的 TF-IDF 实现。"""

    def __init__(self) -> None:
        self.idf_: dict[str, float] = {}
        self.document_count_: int = 0

    def fit(self, documents: list[str]) -> "TfidfVectorizer":
        self.document_count_ = len(documents)
        document_frequency: Counter[str] = Counter()
        for document in documents:
            document_frequency.update(set(tokenize(document)))
        self.idf_ = {
            term: math.log((1 + self.document_count_) / (1 + frequency)) + 1.0
            for term, frequency in document_frequency.items()
        }
        return self

    def transform_one(self, document: str) -> dict[str, float]:
        """将单条文本投影到已拟合词表，并完成 L2 归一化。"""
        counts = Counter(tokenize(document))
        vector = {
            term: (1.0 + math.log(count)) * self.idf_[term]
            for term, count in counts.items()
            if term in self.idf_
        }
        norm = math.sqrt(sum(value * value for value in vector.values()))
        return {term: value / norm for term, value in vector.items()} if norm else {}

    def transform(self, documents: list[str]) -> list[dict[str, float]]:
        return [self.transform_one(document) for document in documents]

    def fit_transform(self, documents: list[str]) -> list[dict[str, float]]:
        return self.fit(documents).transform(documents)

