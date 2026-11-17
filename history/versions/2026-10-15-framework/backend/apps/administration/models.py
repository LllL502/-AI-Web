from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="audit_logs")
    action = models.CharField(max_length=80, db_index=True)
    target_type = models.CharField(max_length=100, db_index=True)
    target_id = models.CharField(max_length=64, db_index=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    ip_digest = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PersistentTask(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "等待"
        RUNNING = "RUNNING", "运行中"
        SUCCEEDED = "SUCCEEDED", "成功"
        FAILED = "FAILED", "失败"

    task_type = models.CharField(max_length=80)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    progress = models.PositiveSmallIntegerField(default=0)
    payload = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.CharField(max_length=1000, blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tasks")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)


class AbuseReport(models.Model):
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reports")
    item = models.ForeignKey("items.Item", on_delete=models.CASCADE, related_name="reports")
    reason = models.CharField(max_length=80)
    detail = models.CharField(max_length=1000, blank=True)
    status = models.CharField(
        max_length=16,
        choices=[("OPEN", "待处理"), ("RESOLVED", "已处理"), ("DISMISSED", "已忽略")],
        default="OPEN",
    )
    created_at = models.DateTimeField(auto_now_add=True)
