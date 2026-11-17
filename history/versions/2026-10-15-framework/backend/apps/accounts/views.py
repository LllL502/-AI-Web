from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import User
from .serializers import LoginSerializer, RegistrationSerializer, UserSerializer


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"data": {"csrf_token": get_token(request)}})


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        return Response({"data": UserSerializer(user, context={"request": request}).data}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if (
            settings.PUBLIC_TEST_MODE
            and serializer.validated_data["username"] in settings.PUBLIC_TEST_BLOCKED_USERNAMES
        ):
            return Response(
                {"error": {"code": "invalid_credentials", "message": "用户名、密码或账户状态无效", "fields": {}, "request_id": request.request_id}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = authenticate(request, **serializer.validated_data)
        if user is None or user.account_status != User.Status.ACTIVE:
            return Response(
                {"error": {"code": "invalid_credentials", "message": "用户名、密码或账户状态无效", "fields": {}, "request_id": request.request_id}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, user)
        return Response({"data": UserSerializer(user, context={"request": request}).data})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"data": UserSerializer(request.user, context={"request": request}).data})

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"data": serializer.data})
