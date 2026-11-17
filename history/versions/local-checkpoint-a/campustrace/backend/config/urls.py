from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from config.maps import AMapProxyView

urlpatterns = [
    path('_AMapService/<path:endpoint>', AMapProxyView.as_view()),
    path("django-admin/", admin.site.urls),
    path("api/v1/", include("config.api_urls")),
]

# 本地桌面版和 Quick Tunnel 测试版没有 Nginx/对象存储，显式提供公开媒体文件。
# 正式部署时 DEBUG 与 PUBLIC_TEST_MODE 均为 False，应由反向代理或对象存储接管。
if settings.DEBUG or settings.PUBLIC_TEST_MODE:
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
