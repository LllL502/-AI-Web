from rest_framework.routers import DefaultRouter

from .views import StationViewSet, StationAccessApplicationViewSet, CampusDirectoryView, CampusFeedbackView, CampusFeedbackReviewView
from django.urls import path

router = DefaultRouter()
router.register("station-applications", StationAccessApplicationViewSet, basename="station-application")
router.register("", StationViewSet, basename="station")
urlpatterns = [path("campuses/", CampusDirectoryView.as_view()), path('campus-feedback/',CampusFeedbackView.as_view()), path('campus-feedback/review/',CampusFeedbackReviewView.as_view()), *router.urls]
