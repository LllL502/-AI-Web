from rest_framework import serializers

from .models import Announcement, HelpArticle, RecoveryStory


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ["id", "title", "slug", "body", "priority", "published_at"]


class HelpArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = HelpArticle
        fields = ["id", "title", "slug", "body", "category", "sort_order", "published_at"]


class RecoveryStorySerializer(serializers.ModelSerializer):
    related_item_title = serializers.CharField(source="related_item.title", read_only=True, allow_null=True)

    class Meta:
        model = RecoveryStory
        fields = ["id", "title", "slug", "body", "related_item_id", "related_item_title", "cover_image", "published_at"]
