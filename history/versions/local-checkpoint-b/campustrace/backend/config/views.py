from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    """同时探测应用与数据库；数据库不可用时健康检查不会伪报成功。"""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        database_ok = cursor.fetchone()[0] == 1
    return JsonResponse({"data": {"status": "ok", "database": database_ok}})
