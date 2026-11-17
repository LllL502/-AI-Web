from django.conf import settings
from django.db import models


class Notification(models.Model):
    campus = models.ForeignKey('stations.Campus', null=True, on_delete=models.PROTECT, related_name='notifications')
    event_key = models.CharField(max_length=200, null=True, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    category = models.CharField(max_length=32)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=1000)
    target_path = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "read_at", "-created_at"], name="notification_inbox_idx")]
