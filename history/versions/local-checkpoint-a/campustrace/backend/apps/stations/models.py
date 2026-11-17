from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError


class School(models.Model):
    name = models.CharField(max_length=100)
    code = models.SlugField(unique=True)
    is_demo = models.BooleanField(default=False)
    official_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    province = models.CharField(max_length=40, blank=True)
    city = models.CharField(max_length=60, blank=True)
    level = models.CharField(max_length=30, blank=True)
    search_text = models.CharField(max_length=500, blank=True)
    source_url = models.URLField(blank=True)
    priority = models.PositiveSmallIntegerField(default=9, db_index=True)
    name_pinyin = models.CharField(max_length=300, blank=True, db_index=True)

    def save(self, *args, **kwargs):
        from pypinyin import lazy_pinyin
        self.name_pinyin = ''.join(lazy_pinyin(self.name)).lower()
        if kwargs.get('update_fields'):
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'name_pinyin'}
        super().save(*args, **kwargs)


class Campus(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name="campuses")
    name = models.CharField(max_length=100)
    code = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)
    verification_status = models.CharField(max_length=16, choices=[('VERIFIED','已核实'),('UNVERIFIED','资料待核实')], default='VERIFIED')
    source_url = models.URLField(blank=True)
    verified_at = models.DateField(null=True, blank=True)


class CampusFeedback(models.Model):
    school = models.ForeignKey(School, on_delete=models.PROTECT, related_name='campus_feedback')
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    campus_name = models.CharField(max_length=100)
    detail = models.TextField(max_length=2000)
    source_url = models.URLField(blank=True)
    status = models.CharField(max_length=16, choices=[('PENDING','待审核'),('APPROVED','已采纳'),('REJECTED','未采纳')], default='PENDING')
    review_note = models.CharField(max_length=500, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='campus_reviews')
    created_at = models.DateTimeField(auto_now_add=True)


def demo_campus_id():
    school, _ = School.objects.get_or_create(code="demo", defaults={"name": "演示学校", "is_demo": True})
    campus, _ = Campus.objects.get_or_create(code="demo-campus", defaults={"school": school, "name": "演示校区"})
    return campus.pk


class CampusLocation(models.Model):
    campus = models.ForeignKey(Campus, on_delete=models.PROTECT, related_name="locations", default=demo_campus_id)
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=64, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    aliases = models.JSONField(default=list, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    public_precision = models.PositiveSmallIntegerField(default=1, help_text="公开位置精度等级")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self):
        if self.parent_id and self.parent.campus_id != self.campus_id:
            raise ValidationError("上级地点必须属于同一校区")


class Station(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "开放"
        BUSY = "BUSY", "繁忙"
        CLOSED = "CLOSED", "暂停服务"

    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=64, unique=True)
    location = models.ForeignKey(CampusLocation, on_delete=models.PROTECT, related_name="stations")
    address = models.CharField(max_length=255)
    opening_hours = models.JSONField(default=dict)
    capacity = models.PositiveIntegerField(default=100)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    contact_phone = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name


class StationMembership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="station_memberships")
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name="memberships")
    can_review = models.BooleanField(default=True)
    can_handover = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "station"], name="uq_station_membership_user_station")
        ]
