from uuid import uuid4


class RequestIdMiddleware:
    """为错误响应与审计日志附加不可预测的请求关联 ID。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = str(uuid4())
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response
