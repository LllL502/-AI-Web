"""线索公开内容的后端自动审核。

这一层只对即将公开的文本做保守的规则筛查：正常内容可以自动
通过；联系方式、外链、广告导流或明显风险内容不会被公开，而是保持
待审核交给人工复核。规则只记录命中类型，不把可能的敏感原文写入日志。

图片在 ``media.py`` 中完成解码、像素限制、元数据移除和安全重编码；
本模块不伪装成图片语义识别服务。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class ModerationResult:
    approved: bool
    reasons: tuple[str, ...] = ()


_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("手机号码", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("电子邮箱", re.compile(r"\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b", re.I)),
    ("网页链接", re.compile(r"(?:https?://|www\.)\S+", re.I)),
    (
        "社交联系方式",
        re.compile(r"(?:微信|wechat|\bwx\b|qq群?|\bqq\b|加我|联系我|扫码|二维码)", re.I),
    ),
    (
        "广告或交易导流",
        re.compile(r"(?:刷单|返利|博彩|赌博|网贷|贷款|套现|代购|兼职招聘|低价出售|转账后)", re.I),
    ),
    ("可执行网页标记", re.compile(r"<\s*(?:script|iframe|object|embed)\b", re.I)),
    ("高风险违禁内容", re.compile(r"(?:毒品交易|枪支弹药|色情服务|炸弹制作)")),
)


def _normalize(value: str | None) -> str:
    return unicodedata.normalize("NFKC", value or "").strip()


def moderate_public_text(*values: str | None) -> ModerationResult:
    """检查会进入广场、搜索和匹配索引的公开文本。"""

    text = "\n".join(_normalize(value) for value in values if value)
    reasons = tuple(label for label, pattern in _RULES if pattern.search(text))
    return ModerationResult(approved=not reasons, reasons=reasons)


def moderate_item(item) -> ModerationResult:
    return moderate_public_text(item.title, item.description, item.brand, item.color)
