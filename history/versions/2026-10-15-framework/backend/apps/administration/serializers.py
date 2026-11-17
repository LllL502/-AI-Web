from math import isclose

from rest_framework import serializers

from apps.accounts.models import User
from apps.content.models import Announcement, HelpArticle
from apps.matching.engine import FACTOR_ORDER
from apps.matching.models import AlgorithmConfig
from apps.stations.models import CampusLocation, Station, StationAccessApplication, StationMembership
from apps.stations.serializers import StationSerializer, StationAccessApplicationSerializer

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
    location_id = serializers.PrimaryKeyRelatedField(
        source="location", queryset=CampusLocation.objects.filter(is_active=True), write_only=True
    )
    members = serializers.SerializerMethodField()

    class Meta(StationSerializer.Meta):
        fields = [
            *StationSerializer.Meta.fields, "location_id", "contact_phone", "is_active", "review_note",
            "members", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "code", "location", "approval_status", "review_note", "members", "created_at", "updated_at"]

    @staticmethod
    def get_members(instance):
        return [
            {
                "id": membership.pk, "user_id": membership.user_id,
                "username": membership.user.username, "display_name": membership.user.display_name,
                "can_review": membership.can_review, "can_handover": membership.can_handover,
                "is_active": membership.is_active,
            }
            for membership in instance.memberships.all()
        ]

    def validate(self, attrs):
        location = attrs.get("location", getattr(self.instance, "location", None))
        request = self.context["request"]
        from apps.stations.scope import selected_campus
        if location and location.campus_id != selected_campus(request):
            raise serializers.ValidationError({"location_id": "服务站地点必须属于当前校区"})
        latitude = attrs.get("latitude", getattr(self.instance, "latitude", None))
        longitude = attrs.get("longitude", getattr(self.instance, "longitude", None))
        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError("地图经纬度必须同时填写")
        if latitude is not None and not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise serializers.ValidationError("地图坐标超出有效范围")
        return attrs


class AdminStationApplicationSerializer(StationAccessApplicationSerializer):
    applicant_username = serializers.CharField(source="applicant.username", read_only=True)

    class Meta(StationAccessApplicationSerializer.Meta):
        fields = [*StationAccessApplicationSerializer.Meta.fields, "applicant_username"]
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
