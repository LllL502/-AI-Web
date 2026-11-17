from django.contrib.auth import password_validation
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    def validate_notification_preferences(self, value):
        if not isinstance(value, dict) or set(value) - {'match','claim'} or not all(isinstance(v, bool) for v in value.values()):
            raise serializers.ValidationError('通知设置必须为有效开关。')
        return value

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "display_name", "role", "account_status", "campus_identifier",
            "phone", "avatar", "notification_preferences", "created_at",
        ]
        read_only_fields = ["id", "username", "role", "account_status", "campus_identifier", "created_at"]


class RegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False, validators=[validate_password])
    display_name = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = User
        fields = ["username", "email", "display_name", "password"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        # 注册页只保留一个用户名字段。display_name 仍保留在数据模型中，
        # 用于兼容历史数据和管理端，新用户默认与 username 一致。
        validated_data["display_name"] = validated_data.pop("display_name", "").strip() or validated_data["username"]
        user = User(**validated_data, role=User.Role.USER)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
