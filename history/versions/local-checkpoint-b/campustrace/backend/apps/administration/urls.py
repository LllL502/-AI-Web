from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AbuseReportViewSet, AdminStationViewSet, AdminUserViewSet, AlgorithmConfigViewSet, AnnouncementAdminViewSet,
    BenchmarkEvidenceView, HelpArticleAdminViewSet, OverviewView, PersistentTaskViewSet,
)

router = DefaultRouter()
router.register("users", AdminUserViewSet, basename="admin-user")
router.register("stations", AdminStationViewSet, basename="admin-station")
router.register("tasks", PersistentTaskViewSet, basename="admin-task")
router.register("abuse-reports", AbuseReportViewSet, basename="admin-abuse-report")
router.register("matching-configs", AlgorithmConfigViewSet, basename="admin-matching-config")
router.register("announcements", AnnouncementAdminViewSet, basename="admin-announcement")
router.register("help", HelpArticleAdminViewSet, basename="admin-help")
urlpatterns = [
    path("overview/", OverviewView.as_view(), name="admin-overview"),
    path("benchmark/", BenchmarkEvidenceView.as_view(), name="admin-benchmark"),
    *router.urls,
]
