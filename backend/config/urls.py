from django.contrib import admin
from django.urls import include, path
from config.maps import AMapProxyView
from apps.items.media_access import ItemMediaView

urlpatterns = [
    path('media/<path:path>', ItemMediaView.as_view()),
    path('_AMapService/<path:endpoint>', AMapProxyView.as_view()),
    path("django-admin/", admin.site.urls),
    path("api/v1/", include("config.api_urls")),
]

