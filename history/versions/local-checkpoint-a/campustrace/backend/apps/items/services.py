from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.administration.models import AuditLog

from .models import Item, ItemRevision
from .moderation import moderate_item


def _snapshot(item: Item) -> dict:
    return {
        "title": item.title,
        "description": item.description,
        "category_id": item.category_id,
        "brand": item.brand,
        "color": item.color,
        "occurred_at": item.occurred_at.isoformat(),
        "location_id": item.location_id,
        "location_detail": item.location_detail,
        "location_candidates": [
            {"location_id": candidate.location_id, "rank": candidate.rank}
            for candidate in item.location_candidates.all()
        ],
        "coordinate_candidates": [
            {
                "label": candidate.label,
                "latitude": str(candidate.latitude),
                "longitude": str(candidate.longitude),
                "coordinate_system": candidate.coordinate_system,
                "rank": candidate.rank,
            }
            for candidate in item.coordinate_candidates.all()
        ],
        "station_id": item.station_id,
    }


@transaction.atomic
def submit_item(item: Item, actor: User, request_id: str = "") -> Item:
    locked = Item.objects.select_for_update().get(pk=item.pk)
    if locked.owner_id != actor.id:
        raise PermissionDenied("只能提交自己的物品")
    if locked.review_status not in {Item.ReviewStatus.DRAFT, Item.ReviewStatus.REJECTED}:
        raise ValidationError("当前审核状态不能再次提交")
    required = [locked.title, locked.description, locked.category_id, locked.location_id, locked.occurred_at]
    if any(value in (None, "") for value in required):
        raise ValidationError("标题、描述、类别、地点和事件时间必须填写")
    next_revision = (locked.revisions.order_by("-revision").values_list("revision", flat=True).first() or 0) + 1
    ItemRevision.objects.create(item=locked, revision=next_revision, snapshot=_snapshot(locked), created_by=actor)
    submitted_at = timezone.now()
    moderation = moderate_item(locked)
    before = {"review_status": locked.review_status, "published_revision": locked.published_revision}
    locked.submitted_at = submitted_at
    if moderation.approved:
        # 正常线索在后端自动通过，无论演示学校还是真实学校都遵循
        # 同一个状态机。评分与日志不包含敏感原文。
        locked.review_status = Item.ReviewStatus.APPROVED
        locked.review_note = "后端自动审核通过"
        locked.published_revision = next_revision
        locked.approved_at = submitted_at
        action = "item.review.auto_approve"
    else:
        # 规则命中时不直接公开，也不仅凭关键词永久驳回；保持待审让
        # 有权人员复核，降低误伤正常失物描述的风险。
        locked.review_status = Item.ReviewStatus.PENDING
        locked.review_note = "自动审核已转人工复核：" + "、".join(moderation.reasons)
        action = "item.review.auto_pending"
    locked.save(
        update_fields=[
            "review_status", "review_note", "published_revision", "approved_at",
            "submitted_at", "updated_at",
        ]
    )
    AuditLog.objects.create(
        actor=actor,
        action=action,
        target_type="items.Item",
        target_id=str(locked.pk),
        before=before,
        after={
            "review_status": locked.review_status,
            "published_revision": locked.published_revision,
            "moderation_reasons": list(moderation.reasons),
        },
        request_id=request_id,
    )
    return locked


@transaction.atomic
def auto_review_pending_item(item: Item, request_id: str = "maintenance") -> Item:
    """将升级前已处于待审的用户线索补跑同一套自动审核。"""

    locked = Item.objects.select_for_update().get(pk=item.pk)
    if locked.review_status != Item.ReviewStatus.PENDING:
        raise ValidationError("只能补审待审核信息")
    latest_revision = locked.revisions.order_by("-revision").first()
    if latest_revision is None:
        raise ValidationError("缺少提交版本，无法自动审核")
    moderation = moderate_item(locked)
    if not moderation.approved:
        locked.review_note = "自动审核已转人工复核：" + "、".join(moderation.reasons)
        locked.save(update_fields=["review_note", "updated_at"])
        return locked

    before = {"review_status": locked.review_status, "published_revision": locked.published_revision}
    locked.review_status = Item.ReviewStatus.APPROVED
    locked.review_note = "后端自动审核通过"
    locked.published_revision = latest_revision.revision
    locked.approved_at = timezone.now()
    locked.save(update_fields=["review_status", "review_note", "published_revision", "approved_at", "updated_at"])
    AuditLog.objects.create(
        actor=locked.owner,
        action="item.review.auto_approve",
        target_type="items.Item",
        target_id=str(locked.pk),
        before=before,
        after={"review_status": locked.review_status, "published_revision": locked.published_revision},
        request_id=request_id,
    )
    return locked


@transaction.atomic
def withdraw_item(item: Item, actor: User, request_id: str = "") -> Item:
    """发布者撤回尚未审核的提交，使其重新回到可编辑草稿状态。"""
    locked = Item.objects.select_for_update().get(pk=item.pk)
    if locked.owner_id != actor.id:
        raise PermissionDenied("只能撤回自己的物品")
    if locked.review_status != Item.ReviewStatus.PENDING:
        raise ValidationError("只有待审核的信息可以撤回")
    locked.review_status = Item.ReviewStatus.DRAFT
    locked.review_note = ""
    locked.submitted_at = None
    locked.save(update_fields=["review_status", "review_note", "submitted_at", "updated_at"])
    AuditLog.objects.create(
        actor=actor,
        action="item.withdraw",
        target_type="items.Item",
        target_id=str(locked.pk),
        before={"review_status": Item.ReviewStatus.PENDING},
        after={"review_status": Item.ReviewStatus.DRAFT},
        request_id=request_id,
    )
    return locked


@transaction.atomic
def delete_item_draft(item: Item, actor: User, request_id: str = "") -> None:
    """只删除从未公开的草稿/驳回记录，并在删除前留下最小审计快照。"""
    locked = Item.objects.select_for_update().get(pk=item.pk)
    if locked.owner_id != actor.id:
        raise PermissionDenied("只能删除自己的草稿")
    if locked.review_status not in {Item.ReviewStatus.DRAFT, Item.ReviewStatus.REJECTED}:
        raise ValidationError("只有草稿或被驳回的信息可以删除")
    item_id = str(locked.pk)
    media_files = [
        (asset.file.storage, asset.file.name, asset.thumbnail.storage, asset.thumbnail.name)
        for asset in locked.media.all()
    ]
    before = {
        "title": locked.title,
        "kind": locked.kind,
        "review_status": locked.review_status,
        "business_status": locked.business_status,
    }
    AuditLog.objects.create(
        actor=actor,
        action="item.delete_draft",
        target_type="items.Item",
        target_id=item_id,
        before=before,
        after={"deleted": True},
        request_id=request_id,
    )
    locked.delete()
    # ImageField 不会在模型级联删除时自动移除磁盘文件；事务成功后再清理，
    # 既避免孤儿文件，也避免数据库回滚却丢失照片。
    for file_storage, file_name, thumb_storage, thumb_name in media_files:
        transaction.on_commit(lambda storage=file_storage, name=file_name: storage.delete(name) if name else None)
        transaction.on_commit(lambda storage=thumb_storage, name=thumb_name: storage.delete(name) if name else None)


@transaction.atomic
def review_item(item: Item, actor: User, approve: bool, note: str, request_id: str = "") -> Item:
    locked = Item.objects.select_for_update().select_related("station").get(pk=item.pk)
    if actor.role not in {User.Role.STAFF, User.Role.ADMIN}:
        raise PermissionDenied("没有审核权限")
    if actor.role == User.Role.STAFF:
        if not locked.station_id or not actor.station_memberships.filter(
            station_id=locked.station_id, is_active=True, can_review=True
        ).exists():
            raise PermissionDenied("物品不在你的站点审核范围")
    if locked.review_status != Item.ReviewStatus.PENDING:
        raise ValidationError("只有待审核信息可以作出审核决定")
    before = {"review_status": locked.review_status, "published_revision": locked.published_revision}
    latest_revision = locked.revisions.order_by("-revision").first()
    if latest_revision is None:
        raise ValidationError("缺少提交版本，无法审核")
    locked.review_status = Item.ReviewStatus.APPROVED if approve else Item.ReviewStatus.REJECTED
    locked.review_note = note.strip()
    if approve:
        locked.published_revision = latest_revision.revision
        locked.approved_at = timezone.now()
    locked.save()
    AuditLog.objects.create(
        actor=actor,
        action="item.review.approve" if approve else "item.review.reject",
        target_type="items.Item",
        target_id=str(locked.pk),
        before=before,
        after={"review_status": locked.review_status, "published_revision": locked.published_revision},
        request_id=request_id,
    )
    return locked


@transaction.atomic
def close_item(item: Item, actor: User, request_id: str = "") -> Item:
    """由发布者或管理员关闭仍在开放的已审核线索，并保留审计证据。"""
    locked = Item.objects.select_for_update().get(pk=item.pk)
    if locked.owner_id != actor.id and actor.role != User.Role.ADMIN:
        raise PermissionDenied("只能关闭自己的物品")
    if locked.review_status != Item.ReviewStatus.APPROVED or locked.business_status != Item.BusinessStatus.OPEN:
        raise ValidationError("只有已审核且开放的物品可以关闭")
    locked.business_status = Item.BusinessStatus.CLOSED
    locked.save(update_fields=["business_status", "updated_at"])
    AuditLog.objects.create(
        actor=actor,
        action="item.close",
        target_type="items.Item",
        target_id=str(locked.pk),
        before={"business_status": Item.BusinessStatus.OPEN},
        after={"business_status": Item.BusinessStatus.CLOSED},
        request_id=request_id,
    )
    return locked
