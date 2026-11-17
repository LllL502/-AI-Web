from rest_framework import serializers

from .models import Announcement, HelpArticle


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ["id", "title", "slug", "body", "priority", "published_at"]


class HelpArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = HelpArticle
        fields = ["id", "title", "slug", "body", "category", "sort_order", "published_at"]
