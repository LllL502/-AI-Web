from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Announcement, HelpArticle, RecoveryStory
from .serializers import AnnouncementSerializer, HelpArticleSerializer, RecoveryStorySerializer


class PublicContentViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]

    def retrieve(self, request, *args, **kwargs):
        return Response({"data": self.get_serializer(self.get_object()).data})


class AnnouncementViewSet(PublicContentViewSet):
    serializer_class = AnnouncementSerializer
    queryset = Announcement.objects.filter(is_published=True).order_by("-priority", "-published_at")


class HelpArticleViewSet(PublicContentViewSet):
    serializer_class = HelpArticleSerializer
    queryset = HelpArticle.objects.filter(is_published=True).order_by("sort_order", "title")


class RecoveryStoryViewSet(PublicContentViewSet):
    serializer_class = RecoveryStorySerializer
    queryset = RecoveryStory.objects.filter(is_published=True, consent_recorded=True).select_related("related_item").order_by("-published_at")
