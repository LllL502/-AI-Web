from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        USER = "USER", "普通用户"
        STAFF = "STAFF", "站点协调员"
        ADMIN = "ADMIN", "系统管理员"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "正常"
        SUSPENDED = "SUSPENDED", "已停用"

    role = models.CharField(max_length=16, choices=Role.choices, default=Role.USER, db_index=True)
    account_status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    display_name = models.CharField(max_length=50)
    campus_identifier = models.CharField(max_length=64, unique=True, null=True, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    avatar = models.ImageField(upload_to="avatars/%Y/%m/", blank=True)
    notification_preferences = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def has_management_role(self) -> bool:
        return self.role in {self.Role.STAFF, self.Role.ADMIN}

    def __str__(self) -> str:
        return self.display_name or self.username
