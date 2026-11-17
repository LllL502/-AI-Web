import uuid
from django.conf import settings
from django.db import models


class AIAdmission(models.Model):
    """A single locked row serializes admission across web workers."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)


class AIJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    campus_id = models.PositiveBigIntegerField()
    action = models.CharField(max_length=80)
    fingerprint = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=64, null=True, blank=True)
    status = models.CharField(max_length=16, default='RUNNING')
    cancel_requested = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True)
    lease_until = models.DateTimeField()
    error_code = models.CharField(max_length=80, blank=True)
    response = models.JSONField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner', 'campus_id', 'action', 'idempotency_key'], name='uq_ai_job_idempotency')]
        indexes = [models.Index(fields=['status', 'lease_until'], name='ai_job_active_idx')]


class ItemVector(models.Model):
    item = models.ForeignKey('items.Item', on_delete=models.CASCADE, related_name='assistant_vectors')
    model_key = models.CharField(max_length=64)
    content_hash = models.CharField(max_length=64)
    dimension = models.PositiveIntegerField()
    vector = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['item', 'model_key'], name='uq_assistant_item_vector')]


class AgentActionReceipt(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    campus_id = models.PositiveBigIntegerField()
    key = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    result = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner', 'campus_id', 'key'], name='uq_agent_action_receipt')]
