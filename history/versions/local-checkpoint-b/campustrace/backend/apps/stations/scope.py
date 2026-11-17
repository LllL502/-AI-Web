"""校区选择只确定数据范围，不授予管理权限；站点权限仍独立校验。"""
from rest_framework.exceptions import ValidationError
from .models import Campus, demo_campus_id


def selected_campus(request):
    value = request.headers.get("X-Campus-ID") or request.query_params.get("campus")
    if not value:
        return demo_campus_id()
    try:
        return Campus.objects.get(pk=int(value), is_active=True).pk
    except (ValueError, TypeError, Campus.DoesNotExist):
        raise ValidationError("请选择有效校区")
