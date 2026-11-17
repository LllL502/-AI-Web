from rest_framework import serializers

from .models import MatchCandidate, MatchRun


class MatchCandidateSerializer(serializers.ModelSerializer):
    item = serializers.SerializerMethodField()

    class Meta:
        model = MatchCandidate
        fields = ["id", "rank", "raw_score", "coverage", "final_score", "factors", "explanation", "is_actionable", "item"]

    def get_item(self, instance):
        item = instance.candidate_item
        return {
            "id": str(item.pk),
            "title": item.title,
            "category": item.category.name,
            "location": item.location.name,
            "occurred_at": item.occurred_at,
            "business_status": item.business_status,
        }


class MatchRunSerializer(serializers.ModelSerializer):
    candidates = MatchCandidateSerializer(many=True, read_only=True)
    config_version = serializers.CharField(source="config.version", read_only=True)
    index_version_name = serializers.CharField(source="index_version.version", read_only=True)

    class Meta:
        model = MatchRun
        fields = [
            "id", "query_item_id", "status", "candidate_count", "config_version", "index_version_name",
            "error_code", "started_at", "completed_at", "created_at", "candidates",
        ]
