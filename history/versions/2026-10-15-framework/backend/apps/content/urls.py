from rest_framework.routers import DefaultRouter

from .views import AnnouncementViewSet, HelpArticleViewSet

router = DefaultRouter()
router.register("announcements", AnnouncementViewSet, basename="announcement")
router.register("help", HelpArticleViewSet, basename="help-article")
urlpatterns = router.urls
