from __future__ import annotations

import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.administration.models import AuditLog
from apps.items.models import Item
from apps.messaging.models import Conversation, ConversationParticipant, Message

from .models import ActiveReservation, Claim, ClaimEvent, HandoverAppointment, ReturnRecord


def _station_staff_can_manage(user: User, claim: Claim, capability: str) -> bool:
    if user.role == User.Role.ADMIN:
        return True
    if user.role != User.Role.STAFF or not claim.found_item.station_id:
        return False
    filters = {"station_id": claim.found_item.station_id, "is_active": True, capability: True}
    return user.station_memberships.filter(**filters).exists()


def _can_review_claim(user: User, claim: Claim) -> bool:
    """已送站物品由站点人员核验；暂未送站时由拾取者先核对私密特征。"""
    if user.role == User.Role.ADMIN:
        return True
    if claim.found_item.station_id:
        return _station_staff_can_manage(user, claim, "can_review")
    return user.id == claim.found_item.owner_id


def _transition(claim: Claim, actor: User, to_status: str, note: str = "", metadata: dict | None = None) -> None:
    from_status = claim.status
    claim.status = to_status
    claim.save(update_fields=["status", "updated_at"])
    ClaimEvent.objects.create(
        claim=claim,
        actor=actor,
        from_status=from_status,
        to_status=to_status,
        note=note,
        metadata=metadata or {},
    )


def _ensure_claim_conversation(claim: Claim) -> Conversation:
    conversation = Conversation.objects.filter(claim=claim).first()
    if conversation:
        return conversation
    conversation = Conversation.objects.create(
        subject=f"认领沟通：{claim.found_item.title}",
        item=claim.found_item,
        claim=claim,
    )
    ConversationParticipant.objects.bulk_create([
        ConversationParticipant(conversation=conversation, user_id=claim.claimant_id),
        ConversationParticipant(conversation=conversation, user_id=claim.found_item.owner_id),
    ])
    Message.objects.create(conversation=conversation, is_system=True, body="认领申请已通过，可以在此协商交接方式。")
    return conversation


@transaction.atomic
def submit_claim(found_item: Item, claimant: User, statement: str, evidence: dict, related_lost_item=None) -> Claim:
    locked_item = Item.objects.select_for_update().get(pk=found_item.pk)
    if locked_item.kind != Item.Kind.FOUND or locked_item.review_status != Item.ReviewStatus.APPROVED:
        raise ValidationError("该物品当前不可认领")
    if locked_item.business_status not in {Item.BusinessStatus.OPEN, Item.BusinessStatus.RESERVED}:
        raise ValidationError("该物品当前不可认领")
    if locked_item.owner_id == claimant.id:
        raise ValidationError("不能认领自己发布的招领物")
    if not related_lost_item:
        raise ValidationError("请先关联自己发布的同类别遗失线索")
    if not statement.strip():
        raise ValidationError("请填写只有失主知道的特征")
    if related_lost_item and related_lost_item.owner_id != claimant.id:
        raise PermissionDenied("关联的遗失信息必须属于当前用户")
    if related_lost_item and related_lost_item.location.campus_id != locked_item.location.campus_id:
        raise ValidationError("认领关联的遗失信息必须属于同一校区")
    if related_lost_item and related_lost_item.category_id != locked_item.category_id:
        raise ValidationError("认领关联的遗失信息必须与招领物品类别一致")
    claim = Claim.objects.create(
        found_item=locked_item,
        claimant=claimant,
        related_lost_item=related_lost_item,
        statement=statement,
        evidence=evidence,
        status=Claim.Status.SUBMITTED,
        submitted_at=timezone.now(),
    )
    ClaimEvent.objects.create(claim=claim, actor=claimant, to_status=Claim.Status.SUBMITTED, note="提交认领申请")
    return claim


@transaction.atomic
def decide_claim(claim: Claim, actor: User, decision: str, note: str, request_id: str = "") -> Claim:
    locked = Claim.objects.select_for_update().select_related("found_item__station").get(pk=claim.pk)
    item = Item.objects.select_for_update().get(pk=locked.found_item_id)
    if not _can_review_claim(actor, locked):
        raise PermissionDenied("认领申请不在你的审核范围")
    allowed = {Claim.Status.SUBMITTED, Claim.Status.NEEDS_INFO}
    if locked.status not in allowed:
        raise ValidationError("当前状态不能作出审核决定")
    target = {"NEEDS_INFO": Claim.Status.NEEDS_INFO, "REJECT": Claim.Status.REJECTED, "APPROVE": Claim.Status.APPROVED}.get(decision)
    if target is None:
        raise ValidationError("未知审核决定")
    if target == Claim.Status.APPROVED:
        if ActiveReservation.objects.select_for_update().filter(found_item=item).exists():
            raise ValidationError("该物品已有有效保留，不能重复批准")
        try:
            ActiveReservation.objects.create(
                found_item=item,
                claim=locked,
                expires_at=timezone.now() + timedelta(days=3),
            )
        except IntegrityError as exc:
            raise ValidationError("该物品已被其他认领保留") from exc
        item.business_status = Item.BusinessStatus.RESERVED
        item.save(update_fields=["business_status", "updated_at"])
        locked.reviewed_by = actor
        locked.decided_at = timezone.now()
        locked.decision_note = note
        locked.save(update_fields=["reviewed_by", "decided_at", "decision_note", "updated_at"])
    _transition(locked, actor, target, note)
    if target == Claim.Status.APPROVED:
        _ensure_claim_conversation(locked)
    AuditLog.objects.create(
        actor=actor,
        action=f"claim.decision.{decision.lower()}",
        target_type="claims.Claim",
        target_id=str(locked.pk),
        before={"status": claim.status},
        after={"status": target},
        request_id=request_id,
    )
    return locked


@transaction.atomic
def schedule_handover(claim: Claim, actor: User, station, scheduled_at) -> tuple[HandoverAppointment, str]:
    locked = Claim.objects.select_for_update().select_related("found_item").get(pk=claim.pk)
    if actor.id != locked.claimant_id and not _station_staff_can_manage(actor, locked, "can_handover"):
        raise PermissionDenied("没有预约该交接的权限")
    if locked.status not in {Claim.Status.APPROVED, Claim.Status.HANDOVER_PENDING}:
        raise ValidationError("只有已批准认领可以预约交接")
    if locked.handover_method == Claim.HandoverMethod.DIRECT:
        raise ValidationError("已选择双方直接交接，不能再预约服务站")
    if scheduled_at <= timezone.now():
        raise ValidationError("预约时间必须晚于当前时间")
    if station.location.campus_id != locked.found_item.location.campus_id:
        raise ValidationError("交接站点必须属于物品所在校区")
    if locked.found_item.station_id and station.id != locked.found_item.station_id:
        raise ValidationError("交接站点必须与保管站点一致")
    if not locked.found_item.station_id:
        # 拾取者暂存的物品在认领通过后才选择交接站。
        # 预约一旦成立，后续的限次码校验与双方确认就由该站点承接。
        item = Item.objects.select_for_update().get(pk=locked.found_item_id)
        item.station = station
        item.save(update_fields=["station", "updated_at"])
    code = f"{secrets.randbelow(1_000_000):06d}"
    appointment, _ = HandoverAppointment.objects.update_or_create(
        claim=locked,
        defaults={
            "station": station,
            "scheduled_at": scheduled_at,
            "code_digest": make_password(code),
            "code_expires_at": min(scheduled_at + timedelta(hours=2), timezone.now() + timedelta(days=3)),
            "failed_attempts": 0,
            "verified_at": None,
            "claimant_confirmed_at": None,
            "staff_confirmed_at": None,
        },
    )
    if locked.status != Claim.Status.HANDOVER_PENDING:
        _transition(locked, actor, Claim.Status.HANDOVER_PENDING, "已预约安全交接")
    locked.handover_method = Claim.HandoverMethod.STATION
    locked.save(update_fields=["handover_method", "updated_at"])
    return appointment, code


@transaction.atomic
def start_direct_handover(claim: Claim, actor: User) -> Claim:
    locked = Claim.objects.select_for_update().select_related("found_item").get(pk=claim.pk)
    if actor.id not in {locked.claimant_id, locked.found_item.owner_id}:
        raise PermissionDenied("不是该认领的交接参与者")
    if locked.status not in {Claim.Status.APPROVED, Claim.Status.HANDOVER_PENDING}:
        raise ValidationError("只有已批准认领可以开始交接")
    if hasattr(locked, "appointment"):
        raise ValidationError("已经预约服务站，不能切换为直接交接")
    locked.handover_method = Claim.HandoverMethod.DIRECT
    locked.save(update_fields=["handover_method", "updated_at"])
    _ensure_claim_conversation(locked)
    if locked.status != Claim.Status.HANDOVER_PENDING:
        _transition(locked, actor, Claim.Status.HANDOVER_PENDING, "已选择双方直接交接")
    return locked


@transaction.atomic
def confirm_direct_handover(claim: Claim, actor: User) -> Claim:
    locked = Claim.objects.select_for_update().select_related("found_item").get(pk=claim.pk)
    item = Item.objects.select_for_update().get(pk=locked.found_item_id)
    if locked.handover_method != Claim.HandoverMethod.DIRECT or locked.status != Claim.Status.HANDOVER_PENDING:
        raise ValidationError("当前认领未进入直接交接")
    now = timezone.now()
    if actor.id == locked.claimant_id:
        locked.claimant_confirmed_at = now
        update_field = "claimant_confirmed_at"
    elif actor.id == item.owner_id:
        locked.finder_confirmed_at = now
        update_field = "finder_confirmed_at"
    else:
        raise PermissionDenied("不是该认领的交接参与者")
    locked.save(update_fields=[update_field, "updated_at"])
    if locked.claimant_confirmed_at and locked.finder_confirmed_at:
        ReturnRecord.objects.get_or_create(
            claim=locked,
            defaults={
                "found_item": item,
                "completed_by": actor,
                "receipt_number": f"CT-{now:%Y%m%d}-{secrets.token_hex(4).upper()}",
                "completed_at": now,
                "metadata": {"handover_method": Claim.HandoverMethod.DIRECT},
            },
        )
        ActiveReservation.objects.filter(claim=locked).delete()
        item.business_status = Item.BusinessStatus.RETURNED
        item.save(update_fields=["business_status", "updated_at"])
        _transition(locked, actor, Claim.Status.COMPLETED, "双方确认直接交接完成")
    return locked


def verify_handover_code(claim: Claim, actor: User, code: str) -> HandoverAppointment:
    # 错误次数必须先提交再抛出 API 校验错误；若在 @atomic 函数内直接抛错，计数会被回滚。
    failure_message = ""
    with transaction.atomic():
        locked = Claim.objects.select_for_update().select_related("found_item").get(pk=claim.pk)
        if actor.id != locked.claimant_id and not _station_staff_can_manage(actor, locked, "can_handover"):
            raise PermissionDenied("没有验证该交接码的权限")
        appointment = HandoverAppointment.objects.select_for_update().get(claim=locked)
        if appointment.verified_at:
            return appointment
        if appointment.failed_attempts >= 5:
            raise ValidationError("交接码尝试次数已达上限，请重新预约")
        if timezone.now() > appointment.code_expires_at:
            raise ValidationError("交接码已过期，请重新预约")
        if not check_password(code, appointment.code_digest):
            appointment.failed_attempts += 1
            appointment.save(update_fields=["failed_attempts", "updated_at"])
            failure_message = f"交接码错误，剩余 {5 - appointment.failed_attempts} 次"
        else:
            appointment.verified_at = timezone.now()
            appointment.save(update_fields=["verified_at", "updated_at"])
            return appointment
    raise ValidationError(failure_message)


@transaction.atomic
def confirm_handover(claim: Claim, actor: User) -> Claim:
    locked = Claim.objects.select_for_update().select_related("found_item").get(pk=claim.pk)
    item = Item.objects.select_for_update().get(pk=locked.found_item_id)
    appointment = HandoverAppointment.objects.select_for_update().get(claim=locked)
    if not appointment.verified_at:
        raise ValidationError("必须先验证交接码")
    now = timezone.now()
    if actor.id == locked.claimant_id:
        appointment.claimant_confirmed_at = now
    elif _station_staff_can_manage(actor, locked, "can_handover"):
        appointment.staff_confirmed_at = now
    else:
        raise PermissionDenied("不是交接参与者")
    appointment.save(update_fields=["claimant_confirmed_at", "staff_confirmed_at", "updated_at"])
    if appointment.claimant_confirmed_at and appointment.staff_confirmed_at and locked.status != Claim.Status.COMPLETED:
        ReturnRecord.objects.create(
            claim=locked,
            found_item=item,
            completed_by=actor,
            receipt_number=f"CT-{now:%Y%m%d}-{secrets.token_hex(4).upper()}",
            completed_at=now,
        )
        ActiveReservation.objects.filter(claim=locked).delete()
        item.business_status = Item.BusinessStatus.RETURNED
        item.save(update_fields=["business_status", "updated_at"])
        _transition(locked, actor, Claim.Status.COMPLETED, "双方确认交接完成")
    return locked
