from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import User


class ActiveSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result and result[0].account_status != User.Status.ACTIVE:
            raise AuthenticationFailed("账号已停用，请联系管理员")
        return result
