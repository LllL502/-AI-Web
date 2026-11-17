from rest_framework import serializers

from .models import CampusLocation, Station, StationAccessApplication


class CampusLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampusLocation
        fields = ["id", "name", "code", "parent_id", "public_precision"]


class StationSerializer(serializers.ModelSerializer):
    location = CampusLocationSerializer(read_only=True)

    class Meta:
        model = Station
        fields = [
            "id", "name", "code", "location", "address", "opening_hours", "capacity", "status",
            "latitude", "longitude", "coordinate_system", "approval_status",
        ]


class StationAccessApplicationSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)
    campus_name = serializers.CharField(source="campus.name", read_only=True)

    class Meta:
        model = StationAccessApplication
        fields = [
            "id", "school", "school_name", "campus", "campus_name", "organization_name", "applicant_name",
            "official_email", "contact_phone", "intended_locations", "evidence_url", "statement", "status",
            "review_note", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "review_note", "created_at", "updated_at"]

    def validate(self, attrs):
        if attrs["campus"].school_id != attrs["school"].id:
            raise serializers.ValidationError({"campus": "校区不属于所选学校"})
        request = self.context.get("request")
        if request and StationAccessApplication.objects.filter(
            applicant=request.user, campus=attrs["campus"], status=StationAccessApplication.Status.PENDING
        ).exists():
            raise serializers.ValidationError("你已有该校区的待核验申请，请勿重复提交")
        return attrs
