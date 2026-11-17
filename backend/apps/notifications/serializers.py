from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "category", "title", "body", "target_path", "metadata", "read_at", "created_at"]
        read_only_fields = fields
