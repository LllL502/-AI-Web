"""寻迹 AI 工作流的严格输入输出协议。

提供方输出必须再经服务端验证，不能把模型返回的 JSON
直接当作业务参数或展示证据。
"""
from collections.abc import Mapping

from django.conf import settings
from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    """拒绝未声明字段，避免模型悄然扩展协议。"""

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = sorted(set(data) - set(self.fields))
            if unknown:
                raise serializers.ValidationError(
                    {"non_field_errors": [f"包含未声明字段：{', '.join(unknown)}"]}
                )
        return super().to_internal_value(data)


class AssistantExtractInputSerializer(StrictSerializer):
    description = serializers.CharField(
        min_length=5,
        max_length=settings.AI_MAX_INPUT_CHARS,
        trim_whitespace=True,
    )
    kind = serializers.ChoiceField(choices=("LOST", "FOUND"), default="LOST")


class StructuredItemDraftSerializer(StrictSerializer):
    FIELD_NAMES = (
        "category_hint",
        "brand",
        "colors",
        "occurred_at",
        "location_hint",
    )

    kind = serializers.ChoiceField(choices=("LOST", "FOUND"))
    title = serializers.CharField(max_length=120)
    category_hint = serializers.CharField(max_length=80, allow_blank=True)
    brand = serializers.CharField(max_length=80, allow_blank=True)
    colors = serializers.ListField(
        child=serializers.CharField(max_length=40),
        allow_empty=True,
        max_length=5,
    )
    occurred_at = serializers.DateTimeField(allow_null=True)
    location_hint = serializers.CharField(max_length=160, allow_blank=True)
    public_description = serializers.CharField(max_length=3000)
    appearance_details = serializers.ListField(child=serializers.CharField(max_length=200), max_length=8, default=list)
    identity_markers = serializers.ListField(child=serializers.ChoiceField(choices=['name','student_number']), max_length=2, default=list)
    uncertain_fields = serializers.ListField(
        child=serializers.ChoiceField(choices=FIELD_NAMES),
        allow_empty=True,
        max_length=len(FIELD_NAMES),
    )
    source_spans = serializers.DictField(
        child=serializers.CharField(max_length=200, allow_blank=True),
        allow_empty=True,
    )

    def validate_source_spans(self, value):
        unknown = sorted(set(value) - {"title", *self.FIELD_NAMES})
        if unknown:
            raise serializers.ValidationError(f"引用了未声明字段：{', '.join(unknown)}")
        return value

    def validate_uncertain_fields(self, value):
        return list(dict.fromkeys(value))


class FollowUpQuestionSerializer(StrictSerializer):
    field = serializers.ChoiceField(choices=StructuredItemDraftSerializer.FIELD_NAMES)
    question = serializers.CharField(max_length=160)
    reason = serializers.CharField(max_length=200)
    required = serializers.BooleanField(default=False)


class ExtractionEnvelopeSerializer(StrictSerializer):
    draft = StructuredItemDraftSerializer()
    follow_up_questions = FollowUpQuestionSerializer(many=True, max_length=3)


class AssistantSearchInputSerializer(StrictSerializer):
    draft = StructuredItemDraftSerializer()
    limit = serializers.IntegerField(min_value=1, max_value=10, default=5)


class PendingDraftInputSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=("LOST", "FOUND"))
    title = serializers.CharField(max_length=120)
    description = serializers.CharField(max_length=3000)
    category = serializers.IntegerField(min_value=1)
    occurred_at = serializers.DateTimeField()
    location = serializers.IntegerField(min_value=1)
    brand = serializers.CharField(max_length=80, allow_blank=True, required=False, default="")
    color = serializers.CharField(max_length=80, allow_blank=True, required=False, default="")
    station = serializers.IntegerField(min_value=1, allow_null=True, required=False, default=None)

