from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ComparisonView, MatchRunViewSet

router = DefaultRouter()
router.register("runs", MatchRunViewSet, basename="match-run")
urlpatterns = [path("compare/", ComparisonView.as_view(), name="match-comparison"), *router.urls]
