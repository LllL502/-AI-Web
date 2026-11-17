"""统一 API 错误封装，避免前端依赖 DRF 的内部错误形状。"""
from uuid import uuid4

from rest_framework.views import exception_handler


def _first_error_message(value):
    """从 DRF 嵌套的字段错误中提取第一条可读信息。"""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        for entry in value:
            message = _first_error_message(entry)
            if message:
                return message
        return ""
    if isinstance(value, dict):
        for entry in value.values():
            message = _first_error_message(entry)
            if message:
                return message
        return ""
    if value is not None:
        return str(value)
    return ""


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    request = context.get("request")
    request_id = getattr(request, "request_id", str(uuid4()))
    # 复制后再 pop，避免修改 DRF 生成的原始错误数据。
    fields = dict(response.data) if isinstance(response.data, dict) else {
        'non_field_errors': response.data
    }
    detail = fields.pop("detail", None)
    workflow_id = None
    task_status = None
    if getattr(request, 'path', '').startswith('/api/v1/assistant/'):
        workflow_id = fields.pop('workflow_id', None)
        if workflow_id:
            task_status = fields.pop('status', None)
    message = _first_error_message(detail) or _first_error_message(fields) or "请求未能完成"
    response.data = {
        "error": {
            "code": getattr(exc, "default_code", "request_failed"),
            "message": message,
            "fields": fields,
            "request_id": request_id,
        }
    }
    if workflow_id:
        response.data['error']['workflow_id'] = workflow_id
    if task_status:
        response.data['error']['task_status'] = task_status
    return response
