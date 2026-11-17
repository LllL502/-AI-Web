from rest_framework.routers import DefaultRouter

from .views import AnnouncementViewSet, HelpArticleViewSet, RecoveryStoryViewSet

router = DefaultRouter()
router.register("announcements", AnnouncementViewSet, basename="announcement")
router.register("help", HelpArticleViewSet, basename="help-article")
router.register("stories", RecoveryStoryViewSet, basename="recovery-story")
urlpatterns = router.urls
