import uuid

from django.conf import settings
from django.db import models


class Claim(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "草稿"
        SUBMITTED = "SUBMITTED", "已提交"
        NEEDS_INFO = "NEEDS_INFO", "待补充"
        APPROVED = "APPROVED", "已批准"
        HANDOVER_PENDING = "HANDOVER_PENDING", "待交接"
        COMPLETED = "COMPLETED", "已完成"
        REJECTED = "REJECTED", "已驳回"
        CANCELLED = "CANCELLED", "已取消"

    class HandoverMethod(models.TextChoices):
        STATION = "STATION", "服务站交接"
        DIRECT = "DIRECT", "双方直接交接"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    found_item = models.ForeignKey("items.Item", on_delete=models.PROTECT, related_name="claims")
    claimant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="claims")
    related_lost_item = models.ForeignKey(
        "items.Item", null=True, blank=True, on_delete=models.PROTECT, related_name="supporting_claims"
    )
    statement = models.TextField(max_length=3000)
    evidence = models.JSONField(default=dict)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT, db_index=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="reviewed_claims"
    )
    decision_note = models.CharField(max_length=1000, blank=True)
    handover_method = models.CharField(max_length=16, choices=HandoverMethod.choices, blank=True)
    claimant_confirmed_at = models.DateTimeField(null=True, blank=True)
    finder_confirmed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    claimant_deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ClaimEvent(models.Model):
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="claim_events")
    from_status = models.CharField(max_length=24, blank=True)
    to_status = models.CharField(max_length=24)
    note = models.CharField(max_length=1000, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class ActiveReservation(models.Model):
    """唯一约束保证同一招领物只有一个有效保留；记录失效时删除该行。"""

    found_item = models.OneToOneField("items.Item", on_delete=models.CASCADE, related_name="active_reservation")
    claim = models.OneToOneField(Claim, on_delete=models.CASCADE, related_name="active_reservation")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class HandoverAppointment(models.Model):
    claim = models.OneToOneField(Claim, on_delete=models.CASCADE, related_name="appointment")
    station = models.ForeignKey("stations.Station", on_delete=models.PROTECT, related_name="appointments")
    scheduled_at = models.DateTimeField()
    code_digest = models.CharField(max_length=128)
    code_expires_at = models.DateTimeField()
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    claimant_confirmed_at = models.DateTimeField(null=True, blank=True)
    staff_confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ReturnRecord(models.Model):
    claim = models.OneToOneField(Claim, on_delete=models.PROTECT, related_name="return_record")
    found_item = models.OneToOneField("items.Item", on_delete=models.PROTECT, related_name="return_record")
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="completed_returns")
    receipt_number = models.CharField(max_length=40, unique=True)
    completed_at = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)
