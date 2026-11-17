from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class AlgorithmConfig(models.Model):
    name = models.CharField(max_length=100)
    version = models.CharField(max_length=32, unique=True)
    weights = models.JSONField()
    thresholds = models.JSONField(default=dict)
    preprocessing = models.JSONField(default=dict)
    is_published = models.BooleanField(default=False, db_index=True)
    active_slot = models.PositiveSmallIntegerField(null=True, unique=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="algorithm_configs")
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous and (previous.is_published or previous.published_at or previous.indexes.exists() or previous.runs.exists()):
                fields = {'name', 'version', 'weights', 'thresholds', 'preprocessing', 'created_by_id'}
                if any(getattr(previous, field) != getattr(self, field) for field in fields):
                    from django.core.exceptions import ValidationError
                    raise ValidationError('已发布或被使用的配置不能修改，请新建版本。')
        self.active_slot = 1 if self.is_published else None
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'active_slot'}
        super().save(*args, **kwargs)

    class Meta:
        constraints = [models.CheckConstraint(condition=(models.Q(is_published=True, active_slot=1, active_slot__isnull=False) | models.Q(is_published=False, active_slot__isnull=True)), name='algorithm_active_slot_consistent')]

    def __str__(self) -> str:
        return f"{self.name} {self.version}"


class AlgorithmPublicationLock(models.Model):
    """The singleton row serializes publication and edits, even on MySQL."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)


class IndexVersion(models.Model):
    version = models.CharField(max_length=64, unique=True)
    document_count = models.PositiveIntegerField()
    vocabulary_size = models.PositiveIntegerField()
    artifact_path = models.CharField(max_length=500)
    corpus_checksum = models.CharField(max_length=64)
    config = models.ForeignKey(AlgorithmConfig, on_delete=models.PROTECT, related_name="indexes")
    is_active = models.BooleanField(default=False, db_index=True)
    built_at = models.DateTimeField(auto_now_add=True)


class MatchRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "等待"
        RUNNING = "RUNNING", "运行中"
        COMPLETED = "COMPLETED", "已完成"
        FAILED = "FAILED", "失败"

    query_item = models.ForeignKey("items.Item", on_delete=models.CASCADE, related_name="match_runs")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="match_runs")
    config = models.ForeignKey(AlgorithmConfig, on_delete=models.PROTECT, related_name="runs")
    index_version = models.ForeignKey(IndexVersion, on_delete=models.PROTECT, related_name="runs")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    candidate_count = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=80, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MatchCandidate(models.Model):
    run = models.ForeignKey(MatchRun, on_delete=models.CASCADE, related_name="candidates")
    candidate_item = models.ForeignKey("items.Item", on_delete=models.CASCADE, related_name="candidate_matches")
    rank = models.PositiveIntegerField()
    raw_score = models.DecimalField(max_digits=7, decimal_places=6, validators=[MinValueValidator(0), MaxValueValidator(1)])
    coverage = models.DecimalField(max_digits=7, decimal_places=6, validators=[MinValueValidator(0), MaxValueValidator(1)])
    final_score = models.DecimalField(max_digits=7, decimal_places=6, validators=[MinValueValidator(0), MaxValueValidator(1)])
    factors = models.JSONField()
    explanation = models.JSONField(default=dict)
    is_actionable = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "candidate_item"], name="uq_run_candidate"),
            models.UniqueConstraint(fields=["run", "rank"], name="uq_run_rank"),
        ]
        ordering = ["run_id", "rank"]


class MatchFeedback(models.Model):
    candidate = models.ForeignKey(MatchCandidate, on_delete=models.CASCADE, related_name="feedback")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="match_feedback")
    label = models.CharField(max_length=32, choices=[("MATCH", "匹配"), ("NOT_MATCH", "不匹配"), ("UNSURE", "不确定")])
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["candidate", "user"], name="uq_candidate_feedback_user")]


class BenchmarkPair(models.Model):
    """只保存明确标注的合成基准关系，不从认领结果偷渡训练标签。"""

    lost_item = models.ForeignKey("items.Item", on_delete=models.CASCADE, related_name="benchmark_lost_pairs")
    found_item = models.ForeignKey("items.Item", on_delete=models.CASCADE, related_name="benchmark_found_pairs")
    is_match = models.BooleanField()
    split = models.CharField(max_length=16, choices=[("TRAIN", "训练"), ("VALIDATION", "验证"), ("TEST", "测试")])
    is_synthetic = models.BooleanField(default=True)
    source_note = models.CharField(max_length=255, default="固定规则生成的演示基准")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["lost_item", "found_item"], name="uq_benchmark_lost_found")
        ]
