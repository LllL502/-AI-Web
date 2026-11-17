"""面向校园失物语料的中文文本预处理。

算法不依赖在线服务。流程为：全角/大小写归一化 → 同义词归一 →
正则切块 → 校园领域词典正向最大匹配 → 停用词过滤。对词典未覆盖的
连续中文片段补充二元字组，从而在保持可解释性的同时降低未登录词风险。
"""

from __future__ import annotations

import re
import unicodedata


STOPWORDS = {
    "的", "了", "是", "在", "有", "和", "与", "于", "我", "一个", "一只",
    "一件", "这个", "那个", "请", "同学", "看到", "发现", "丢失", "捡到",
    "遗失", "拾到", "物品", "东西", "联系", "谢谢", "大约", "左右",
    "寻找", "上有", "内有", "挂着", "上面", "侧面", "里面",
}

# 竞赛项目使用可审查的领域词典；最长词优先，避免“校园卡”被拆成三个字。
DOMAIN_WORDS = {
    "校园卡", "学生卡", "一卡通", "身份证", "银行卡", "交通卡", "图书证",
    "双肩包", "帆布包", "手提包", "斜挎包", "钱包", "卡包", "钥匙扣",
    "笔记本电脑", "平板电脑", "充电宝", "充电器", "数据线", "耳机盒",
    "蓝牙耳机", "无线耳机", "有线耳机", "手机", "相机", "鼠标", "键盘",
    "保温杯", "水杯", "雨伞", "眼镜盒", "眼镜", "手表", "戒指", "项链",
    "教材", "笔记本", "文件夹", "文具袋", "钢笔", "U盘", "优盘",
    "黑色", "白色", "灰色", "银色", "红色", "蓝色", "绿色", "黄色",
    "粉色", "紫色", "棕色", "透明", "深蓝", "浅蓝", "玫瑰金",
    "教学楼", "实验楼", "图书馆", "体育馆", "操场", "食堂", "宿舍楼",
    "快递站", "校门", "报告厅", "自习室", "阶梯教室", "创新中心",
    "一楼", "二楼", "三楼", "四楼", "五楼", "门口", "座位", "走廊",
    "苹果", "华为", "小米", "荣耀", "联想", "戴尔", "惠普", "耐克",
    "阿迪达斯", "小熊挂件", "挂件", "贴纸", "划痕", "编号", "姓名",
    "上面", "侧面", "里面",
}

SYNONYMS = {
    "一卡通": "校园卡", "学生卡": "校园卡", "饭卡": "校园卡",
    "拾到": "发现", "捡到": "发现", "遗失": "丢失",
    "无线耳机": "蓝牙耳机", "优盘": "U盘", "移动电源": "充电宝",
    "教学大楼": "教学楼", "饭堂": "食堂", "寝室": "宿舍",
}

_BLOCK_RE = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z]+(?:[-_][a-zA-Z0-9]+)*|\d+")
_MAX_WORD_LEN = max(map(len, DOMAIN_WORDS))


def normalize_text(text: str) -> str:
    """统一全半角、英文字母大小写和已知同义表达。"""
    normalized = unicodedata.normalize("NFKC", text or "").lower().strip()
    # 校园地点中“2楼/二楼”混写很常见，先归一化再做地点相似度。
    floor_aliases = {"1楼": "一楼", "2楼": "二楼", "3楼": "三楼", "4楼": "四楼", "5楼": "五楼"}
    for source, target in floor_aliases.items():
        normalized = normalized.replace(source, target)
    for source, target in sorted(SYNONYMS.items(), key=lambda pair: len(pair[0]), reverse=True):
        normalized = normalized.replace(source.lower(), target.lower())
    return normalized


def _segment_chinese(block: str) -> list[str]:
    """正向最大匹配；连续未知片段用二元字组提供柔性召回。"""
    tokens: list[str] = []
    unknown: list[str] = []

    def flush_unknown() -> None:
        if not unknown:
            return
        raw = "".join(unknown)
        # 单字保留；多字未知词加入二元字组，可匹配“定制徽章”等新表达。
        tokens.extend([raw] if len(raw) <= 2 else [raw[i:i + 2] for i in range(len(raw) - 1)])
        unknown.clear()

    index = 0
    while index < len(block):
        matched = ""
        for size in range(min(_MAX_WORD_LEN, len(block) - index), 1, -1):
            candidate = block[index:index + size]
            if candidate in DOMAIN_WORDS:
                matched = candidate
                break
        if matched:
            flush_unknown()
            tokens.append(matched)
            index += len(matched)
        else:
            unknown.append(block[index])
            index += 1
    flush_unknown()
    return tokens


def tokenize(text: str) -> list[str]:
    """输出去停用词后的可解释 token 列表。"""
    tokens: list[str] = []
    for block in _BLOCK_RE.findall(normalize_text(text)):
        block_tokens = _segment_chinese(block) if re.fullmatch(r"[\u4e00-\u9fff]+", block) else [block]
        tokens.extend(token for token in block_tokens if token not in STOPWORDS and len(token.strip()) > 0)
    return tokens
