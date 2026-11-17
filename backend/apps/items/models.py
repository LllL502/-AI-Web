import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=64, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    synonyms = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class Item(models.Model):
    class Kind(models.TextChoices):
        LOST = "LOST", "遗失"
        FOUND = "FOUND", "招领"

    class ReviewStatus(models.TextChoices):
        DRAFT = "DRAFT", "草稿"
        PENDING = "PENDING", "待审核"
        APPROVED = "APPROVED", "已通过"
        REJECTED = "REJECTED", "已驳回"

    class BusinessStatus(models.TextChoices):
        OPEN = "OPEN", "寻找中"
        RESERVED = "RESERVED", "认领保留中"
        RETURNED = "RETURNED", "已归还"
        CLOSED = "CLOSED", "已关闭"
        EXPIRED = "EXPIRED", "已过期"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="items")
    kind = models.CharField(max_length=8, choices=Kind.choices, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="items")
    title = models.CharField(max_length=120)
    description = models.TextField(max_length=3000)
    brand = models.CharField(max_length=80, blank=True)
    color = models.CharField(max_length=80, blank=True)
    occurred_at = models.DateTimeField(db_index=True)
    location = models.ForeignKey("stations.CampusLocation", on_delete=models.PROTECT, related_name="items")
    location_detail = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    coordinate_system = models.CharField(max_length=10, blank=True, choices=[('GCJ02','高德GCJ-02')])
    station = models.ForeignKey(
        "stations.Station", null=True, blank=True, on_delete=models.PROTECT, related_name="items"
    )
    review_status = models.CharField(
        max_length=16, choices=ReviewStatus.choices, default=ReviewStatus.DRAFT, db_index=True
    )
    business_status = models.CharField(
        max_length=16, choices=BusinessStatus.choices, default=BusinessStatus.OPEN, db_index=True
    )
    review_note = models.CharField(max_length=500, blank=True)
    published_revision = models.PositiveIntegerField(null=True, blank=True)
    is_demo = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["kind", "review_status", "business_status", "-occurred_at"], name="item_public_feed_idx"),
            models.Index(fields=["owner", "-created_at"], name="item_owner_created_idx"),
        ]

    @property
    def searchable_text(self) -> str:
        return " ".join(part for part in [self.title, self.description, self.brand, self.color] if part)

    def __str__(self) -> str:
        return f"{self.get_kind_display()}：{self.title}"


class ItemLocationCandidate(models.Model):
    """受保护的结构化地点。

    遗失线索可以按“可能性”保存最多 5 个地点；招领线索只保存
    1 个已知拾获地点。这些数据不进入公开列表，只在授权流程与匹配
    计算中使用。rank 越小表示越可能，不把主观顺序伪装成精确概率。
    """

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="location_candidates")
    location = models.ForeignKey(
        "stations.CampusLocation", on_delete=models.PROTECT, related_name="item_location_candidates"
    )
    rank = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["rank", "id"]
        constraints = [
            models.UniqueConstraint(fields=["item", "location"], name="uq_item_location_candidate"),
            models.UniqueConstraint(fields=["item", "rank"], name="uq_item_location_rank"),
        ]


class ItemCoordinateCandidate(models.Model):
    """真实地图上的受保护候选坐标。

    地图坐标与结构化的演示地点分开保存：前者用于真实校园的高德地图，
    后者用于不依赖真实坐标的演示校区。两者都只在授权流程和匹配计算中
    使用，公开广场不会返回坐标或候选名称。
    """

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="coordinate_candidates")
    label = models.CharField(max_length=160, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    coordinate_system = models.CharField(
        max_length=10,
        default="GCJ02",
        choices=[("GCJ02", "高德GCJ-02")],
    )
    rank = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["rank", "id"]
        constraints = [
            models.UniqueConstraint(fields=["item", "rank"], name="uq_item_coordinate_rank"),
            models.UniqueConstraint(
                fields=["item", "latitude", "longitude"],
                name="uq_item_coordinate_candidate",
            ),
        ]


class ItemRevision(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="revisions")
    revision = models.PositiveIntegerField()
    snapshot = models.JSONField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="item_revisions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["item", "revision"], name="uq_item_revision_number")]
        ordering = ["item_id", "revision"]


class MediaAsset(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="media")
    file = models.ImageField(upload_to="items/%Y/%m/%d/")
    thumbnail = models.ImageField(upload_to="items/thumbs/%Y/%m/%d/", blank=True)
    sha256 = models.CharField(max_length=64, db_index=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PrivateClue(models.Model):
    """敏感特征只存摘要，不通过普通序列化器回传原文。"""

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="private_clues")
    prompt = models.CharField(max_length=255)
    answer_digest = models.CharField(max_length=128)
    answer_hint = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "item"], name="uq_favorite_user_item")]


class Subscription(models.Model):
    campus = models.ForeignKey('stations.Campus', null=True, on_delete=models.PROTECT, related_name='subscriptions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions")
    name = models.CharField(max_length=100)
    criteria = models.JSONField(default=dict)
    minimum_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=0.65,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
