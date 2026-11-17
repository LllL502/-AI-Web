"""LLM 提供方适配与可明确识别的本地开发模式。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import APIException

from .contracts import ExtractionEnvelopeSerializer
from .publication import clean_source, compose_public_draft, resolve_time_evidence


class ProviderUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "AI 服务当前不可用，请使用普通表单继续。"
    default_code = "ai_provider_unavailable"


class ProviderProtocolError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "AI 返回的结构未通过校验，未写入任何业务数据。"
    default_code = "ai_protocol_error"


@dataclass(frozen=True)
class ProviderResult:
    payload: dict
    provider: str
    model: str
    simulated: bool


def redact_sensitive_text(value: str) -> str:
    """进入模型前的最小脱敏，也用于开发模式输出。"""
    value = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号已隐藏]", value)
    value = re.sub(r"(?<!\d)\d{17}[\dXx](?!\d)", "[证件号已隐藏]", value)
    value = re.sub(r'(学号|学生编号|学生号)\s*(?:是|为|[:：])?\s*[0-9A-Za-z-]{4,24}', r'\1[学号已隐藏]', value)
    value = re.sub(r'(姓名|名字)\s*(?:是|为|叫|[:：])\s*[\u4e00-\u9fff]{2,4}(?=[，,。；;\s]|$)', r'\1[姓名已隐藏]', value)
    value = re.sub(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        "[邮箱已隐藏]",
        value,
    )
    return value


def _clean_json_content(content: str) -> dict:
    value = content.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("provider response is not an object")
    return parsed


class DevelopmentStubProvider:
    """
    不调用模型的确定性规则桩。

    返回结果始终带 ``simulated=True``，前后端必须显示开发标识。
    """

    CATEGORY_KEYWORDS = {
        "钥匙": ("钥匙", "钥匙串"),
        "耳机": ("耳机", "耳麦", "充电盒"),
        "校园卡": ("校园卡", "一卡通", "学生卡"),
        "手机": ("手机",),
        "电脑": ("电脑", "笔记本"),
        "水杯": ("水杯", "保温杯", "杯子"),
        "雨伞": ("雨伞", "伞"),
        "背包": ("背包", "书包"),
        "证件": ("身份证", "驾驶证", "证件"),
    }
    COLORS = ("黑色", "白色", "银色", "灰色", "红色", "蓝色", "绿色", "黄色", "粉色", "紫色", "橙色", "金色")
    BRANDS = ("Sony", "Apple", "AirPods", "华为", "小米", "荣耀", "OPPO", "vivo", "联想", "戴尔")
    LOCATION_PATTERN = re.compile(
        r"([\u4e00-\u9fffA-Za-z0-9]{0,8}(?:图书馆|食堂|体育馆|操场|教学楼|宿舍|校门|服务站))"
    )

    def extract(self, description: str, kind: str) -> ProviderResult:
        safe_text = redact_sensitive_text(description.strip())
        category = next(
            (
                name
                for name, keywords in self.CATEGORY_KEYWORDS.items()
                if any(keyword.lower() in safe_text.lower() for keyword in keywords)
            ),
            "",
        )
        colors = [color for color in self.COLORS if color in safe_text]
        brand = next((name for name in self.BRANDS if name.lower() in safe_text.lower()), "")
        location_match = self.LOCATION_PATTERN.search(safe_text)
        location = location_match.group(1) if location_match else ""
        action = "寻找" if kind == "LOST" else "拾到"
        subject = category or "物品"
        title = f"{action}{subject}：{safe_text[:60]}"[:120]

        uncertain = [
            field
            for field, missing in (
                ("category_hint", not category),
                ("occurred_at", True),
                ("location_hint", not location),
            )
            if missing
        ]
        questions = []
        question_map = {
            "category_hint": ("这件物品大致属于哪一类？", "类别会直接缩小候选范围。"),
            "occurred_at": ("大约是什么时间遗失或拾到的？", "时间先后用于排除明显冲突。"),
            "location_hint": ("最可能在校园的哪个区域？", "地点只用于同校区候选排序，不会公开私密坐标。"),
        }
        for field in uncertain[:3]:
            question, reason = question_map[field]
            questions.append({"field": field, "question": question, "reason": reason, "required": False})

        spans = {"title": safe_text[:60]}
        if category:
            spans["category_hint"] = category
        if brand:
            spans["brand"] = brand
        if colors:
            spans["colors"] = colors[0]
        if location:
            spans["location_hint"] = location

        return ProviderResult(
            payload={
                "draft": {
                    "kind": kind,
                    "title": title,
                    "category_hint": category,
                    "brand": brand,
                    "colors": colors,
                    "occurred_at": None,
                    "location_hint": location,
                    "public_description": safe_text,
                    "appearance_details": [part.strip() for part in re.split(r'[，,。；;\n]', safe_text)
                        if re.search(r'划痕|磨损|贴纸|挂件|材质|皮革|塑料|金属|大小|尺寸|A4|A5|没有挂|不带', part)][:8],
                    "uncertain_fields": uncertain,
                    "source_spans": spans,
                },
                "follow_up_questions": questions,
            },
            provider="development_stub",
            model="local_rules_v1",
            simulated=True,
        )


class OpenAICompatibleProvider:
    """通用 OpenAI-compatible 结构化输出适配，默认不启用。"""

    def __init__(self):
        self.base_url = settings.AI_PROVIDER_BASE_URL.rstrip("/")
        self.api_key = settings.AI_PROVIDER_API_KEY
        self.model = settings.AI_PROVIDER_MODEL
        if not self.base_url or not self.api_key or not self.model:
            raise ProviderUnavailable("模型提供方未完成本地配置。")
        parsed = url_parse.urlparse(self.base_url)
        local_debug = settings.DEBUG and parsed.hostname in {"127.0.0.1", "localhost"}
        if parsed.scheme != "https" and not local_debug:
            raise ProviderUnavailable("模型提供方地址必须使用 HTTPS。")

    def extract(self, description: str, kind: str) -> ProviderResult:
        safe_text = redact_sensitive_text(description)
        system_prompt = (
            "你是校园失物描述结构化器。只能依据用户原文，不猜测品牌、时间或地点。"
            "只返回 JSON 对象，且必须符合给定结构。occurred_at 不确定时返回 null。"
            "category_hint、brand、colors每项、location_hint必须直接摘录原文中的连续文字，不能归一化或翻译。"
            "source_spans对应字段必须逐字引用原文，未知字段用空字符串或空数组，不得虚构。"
            "uncertain_fields只能从category_hint、brand、colors、occurred_at、location_hint中逐项选择。"
            "follow_up_questions 最多 3 个，只询问会改变检索结果的字段。"
            "appearance_details提取外观、大小、材质、磨损、贴纸、挂件等有效短语，必须逐字摘录原文，保留否定和不确定限定。"
            "不要摘录聊天提示、发布指令、联系方式、情绪或重复信息；不得把别人的物品特征当作用户的。"
            "时间、地点和类别分别填入对应字段，不混入appearance_details。"
            "输入可能来自多轮交流，后面的明确更正覆盖前面的同一属性，保留其他未更正的信息；不能把已更正的旧颜色、旧品牌同时保留。"
            "袋子里面、口袋里或容器内装的物品是附属特征，不是更换寻物主体；只有明确更正主体时才替换类别。"
            "时间只需要逐字摘录到source_spans.occurred_at。occurred_at始终返回null，由程序解析时间；禁止自行推算或填当前时间。"
            "source_spans的每个值都是原文字符串，colors的引用也是字符串，不能是数组。"
        )
        schema_hint = {
            "draft": {
                "kind": kind,
                "title": "string",
                "category_hint": "string",
                "brand": "string",
                "colors": ["string"],
                "occurred_at": None,
                "location_hint": "string",
                "public_description": "string",
                "appearance_details": ["逐字摘录原文中的外观、材质、尺寸、磨损、挂件或贴纸等短语，保留否定和不确定词"],
                "uncertain_fields": ["occurred_at"],
                "source_spans": {"category_hint": "", "brand": "", "colors": "", "occurred_at": "", "location_hint": ""},
            },
            "follow_up_questions": [
                {"field": "occurred_at", "question": "string", "reason": "string", "required": False}
            ],
        }
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"kind": kind, "description": safe_text, "output_example": schema_hint},
                            ensure_ascii=False,
                        ),
                    },
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = url_request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            from .runtime import check_budget
            with url_request.urlopen(request, timeout=check_budget(settings.AI_REQUEST_TIMEOUT_SECONDS)) as response:
                data = json.loads(response.read().decode("utf-8"))
            check_budget()
            content = data["choices"][0]["message"]["content"]
            payload = _clean_json_content(content)
        except (url_error.URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            from .runtime import check_budget
            check_budget()
            raise ProviderUnavailable() from None
        return ProviderResult(
            payload=payload,
            provider="openai_compatible",
            model=self.model,
            simulated=False,
        )


def get_provider():
    mode = settings.AI_PROVIDER_MODE
    if mode == "development_stub":
        return DevelopmentStubProvider()
    if mode == "openai_compatible":
        return OpenAICompatibleProvider()
    if mode == "disabled":
        raise ProviderUnavailable("当前未启用 AI 提供方，请使用普通表单。")
    raise ProviderUnavailable("未识别的 AI 提供方模式。")


def _ground_dialogue_payload(payload, source, kind):
    """Keep independently verifiable slots; one bad slot cannot break a chat."""
    raw = payload.get('draft') if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        raise ProviderProtocolError()
    draft = {'kind':kind,'title':'物品','public_description':source,'category_hint':'','brand':'',
        'colors':[],'location_hint':'','occurred_at':None,'appearance_details':[],
        'uncertain_fields':[],'source_spans':{}}
    for field, limit in [('category_hint',80),('brand',80),('location_hint',160)]:
        value=raw.get(field)
        if isinstance(value,str) and 0 < len(value)<=limit and value in source:
            draft[field]=value;draft['source_spans'][field]=value
    colors=raw.get('colors',[])
    if isinstance(colors,str):colors=[colors]
    if isinstance(colors,list):
        draft['colors']=list(dict.fromkeys(value for value in colors if isinstance(value,str) and 0<len(value)<=40 and value in source))[:5]
        if draft['colors']:draft['source_spans']['colors']=draft['colors'][0]
    details=raw.get('appearance_details',[])
    if isinstance(details,list):
        draft['appearance_details']=list(dict.fromkeys(value for value in details if isinstance(value,str) and 0<len(value)<=200 and value in source))[:8]
    spans=raw.get('source_spans',{})
    span=spans.get('occurred_at','') if isinstance(spans,dict) else ''
    if not isinstance(span,str) or not span or span not in source:
        span=raw.get('occurred_at','')
    if isinstance(span,str) and span and len(span)<=200 and span in source:
        draft['source_spans']['occurred_at']=span
    fields={'category_hint','brand','colors','location_hint','occurred_at'}
    unknown=raw.get('uncertain_fields',[])
    if isinstance(unknown,list):draft['uncertain_fields']=[value for value in unknown if isinstance(value,str) and value in fields]
    return {'draft':draft,'follow_up_questions':[]}


def extract_structured_description(description: str, kind: str, *, tolerant=False) -> ProviderResult:
    safe_description = redact_sensitive_text(clean_source(description))
    result = get_provider().extract(safe_description, kind)
    normalized = _ground_dialogue_payload(result.payload,safe_description,kind) if tolerant else dict(result.payload)
    if isinstance(normalized.get("draft"), dict):
        normalized["draft"] = dict(normalized["draft"])
        # These fields belong to the application, not the model. Populate them
        # before validation so an empty generated title cannot block valid facts.
        normalized["draft"]["title"] = f"{'寻找' if kind == 'LOST' else '拾到'}物品：{safe_description[:60]}"[:120]
        normalized["draft"]["public_description"] = safe_description
        from .identity_features import identity_markers
        normalized['draft']['identity_markers'] = identity_markers(safe_description) if '卡' in str(normalized['draft'].get('category_hint') or '') else []
        spans = normalized['draft'].get('source_spans', {})
        time_span = spans.get('occurred_at', '') if isinstance(spans, dict) else ''
        raw_time = normalized['draft'].get('occurred_at')
        if raw_time and (not isinstance(time_span, str) or not time_span or time_span not in safe_description):
            raise ProviderProtocolError('时间未能对应用户原话，请核对。')
        resolved_time = resolve_time_evidence(time_span) if isinstance(time_span, str) and time_span in safe_description else None
        normalized['draft']['occurred_at'] = resolved_time.isoformat() if resolved_time else None
        if resolved_time is None:
            uncertain = normalized['draft'].get('uncertain_fields', [])
            if isinstance(uncertain, list):
                normalized['draft']['uncertain_fields'] = list(dict.fromkeys([*uncertain, 'occurred_at']))
    validator = ExtractionEnvelopeSerializer(data=normalized)
    try:
        validator.is_valid(raise_exception=True)
    except serializers.ValidationError:
        raise ProviderProtocolError() from None
    payload = validator.validated_data
    draft = payload["draft"]
    if draft["kind"] != kind:
        raise ProviderProtocolError()
    source_spans = draft["source_spans"]
    grounded_fields = {
        "category_hint": draft["category_hint"],
        "brand": draft["brand"],
        "colors": draft["colors"],
        "occurred_at": draft["occurred_at"],
        "location_hint": draft["location_hint"],
    }
    for field, value in grounded_fields.items():
        if value in (None, "", []):
            continue
        span = source_spans.get(field, "")
        if not span or span not in safe_description:
            raise ProviderProtocolError()
        if field == "colors":
            if any(color.lower() not in safe_description.lower() for color in value):
                raise ProviderProtocolError()
        elif field != "occurred_at" and str(value).lower() not in safe_description.lower():
            raise ProviderProtocolError()
    try:
        compose_public_draft(draft, safe_description)
    except ValueError:
        raise ProviderProtocolError('外观细节未能对应用户原话，请重试。') from None
    return ProviderResult(
        payload=payload,
        provider=result.provider,
        model=result.model,
        simulated=result.simulated,
    )

