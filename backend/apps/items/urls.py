from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import FavoriteViewSet, ItemMapSummaryView, ItemMetadataView, ItemViewSet, SubscriptionViewSet

router = DefaultRouter()
router.register("favorites", FavoriteViewSet, basename="favorite")
router.register("subscriptions", SubscriptionViewSet, basename="subscription")
router.register("", ItemViewSet, basename="item")
urlpatterns = [
    path("metadata/", ItemMetadataView.as_view(), name="item-metadata"),
    path("map-summary/", ItemMapSummaryView.as_view(), name="item-map-summary"),
    *router.urls,
]
