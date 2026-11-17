from math import isclose

from rest_framework import serializers

from apps.accounts.models import User
from apps.content.models import Announcement, HelpArticle
from apps.matching.engine import FACTOR_ORDER
from apps.matching.models import AlgorithmConfig
from apps.stations.serializers import StationSerializer

from .models import AbuseReport, PersistentTask


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "display_name", "email", "role", "account_status", "created_at", "updated_at"]
        read_only_fields = ["id", "username", "email", "display_name", "created_at", "updated_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        if self.instance and request and self.instance.pk == request.user.pk:
            if attrs.get("role", self.instance.role) != User.Role.ADMIN or attrs.get("account_status") == User.Status.SUSPENDED:
                raise serializers.ValidationError("不能降级或停用当前管理员账号")
        return attrs


class PersistentTaskSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.CharField(source="requested_by.display_name", read_only=True)

    class Meta:
        model = PersistentTask
        fields = [
            "id", "task_type", "status", "progress", "payload", "result", "error_code", "error_message",
            "requested_by_name", "created_at", "started_at", "finished_at",
        ]
        read_only_fields = fields


class AdminStationSerializer(StationSerializer):
    """后台站点只读视图；写操作留给带审计的独立流程。"""

    class Meta(StationSerializer.Meta):
        fields = [*StationSerializer.Meta.fields, "contact_phone", "is_active", "created_at", "updated_at"]
        read_only_fields = fields


class AbuseReportSerializer(serializers.ModelSerializer):
    reporter_name = serializers.CharField(source="reporter.display_name", read_only=True)
    item_title = serializers.CharField(source="item.title", read_only=True)

    class Meta:
        model = AbuseReport
        fields = ["id", "reporter_name", "item_id", "item_title", "reason", "detail", "status", "created_at"]
        read_only_fields = ["id", "reporter_name", "item_id", "item_title", "reason", "detail", "created_at"]


class AlgorithmConfigSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.display_name", read_only=True)

    class Meta:
        model = AlgorithmConfig
        fields = [
            "id", "name", "version", "weights", "thresholds", "preprocessing", "is_published",
            "created_by_name", "created_at", "published_at",
        ]
        read_only_fields = ["id", "is_published", "created_by_name", "created_at", "published_at"]

    def validate_weights(self, value):
        if set(value) != set(FACTOR_ORDER):
            raise serializers.ValidationError("必须提供完整六因子权重")
        numeric = {key: float(entry) for key, entry in value.items()}
        if any(entry < 0 for entry in numeric.values()) or not isclose(sum(numeric.values()), 1.0, abs_tol=1e-9):
            raise serializers.ValidationError("权重必须非负且总和为 1")
        return numeric


class AnnouncementAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = "__all__"
        read_only_fields = ["created_by"]


class HelpArticleAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = HelpArticle
        fields = "__all__"
        read_only_fields = ["created_by"]
