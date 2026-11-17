from django.urls import include, path

from config.views import health
from config.maps import MapConfigView, CampusRegionView, CampusDiscoveryView

urlpatterns = [
    path("health/", health, name="health"),
    path('maps/config/',MapConfigView.as_view()),
    path('maps/discover-campuses/',CampusDiscoveryView.as_view()),
    path('maps/campus-region/',CampusRegionView.as_view()),
    path("auth/", include("apps.accounts.urls")),
    path("items/", include("apps.items.urls")),
    path("matches/", include("apps.matching.urls")),
    path("claims/", include("apps.claims.urls")),
    path("stations/", include("apps.stations.urls")),
    path("messages/", include("apps.messaging.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("content/", include("apps.content.urls")),
    path("admin/", include("apps.administration.urls")),
]
