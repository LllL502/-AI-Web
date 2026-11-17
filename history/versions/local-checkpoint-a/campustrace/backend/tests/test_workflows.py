from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.administration.models import AuditLog
from apps.claims.models import ActiveReservation, Claim, ReturnRecord
from apps.claims.services import (
    confirm_direct_handover,
    confirm_handover,
    decide_claim,
    schedule_handover,
    start_direct_handover,
    submit_claim,
    verify_handover_code,
)
from apps.items.models import Category, Item, ItemRevision
from apps.items.services import review_item
from apps.messaging.models import Conversation
from apps.stations.models import CampusLocation, Station, StationMembership

pytestmark = pytest.mark.mysql


@pytest.fixture
def domain(db):
    category = Category.objects.create(name="耳机", code="headphones")
    location = CampusLocation.objects.create(name="图书馆", code="library")
    other_location = CampusLocation.objects.create(name="体育馆", code="gym")
    station = Station.objects.create(name="图书馆服务点", code="library-station", location=location, address="一楼")
    other_station = Station.objects.create(name="体育馆服务点", code="gym-station", location=other_location, address="东门")
    owner = User.objects.create_user("owner", password="SafePassword!1", display_name="发布者")
    claimant = User.objects.create_user("claimant", password="SafePassword!1", display_name="领取人")
    claimant_two = User.objects.create_user("claimant2", password="SafePassword!1", display_name="领取人二")
    staff = User.objects.create_user("staff", password="SafePassword!1", display_name="协调员", role=User.Role.STAFF)
    StationMembership.objects.create(user=staff, station=station, can_review=True, can_handover=True)
    return {
        "category": category, "location": location, "other_location": other_location,
        "station": station, "other_station": other_station, "owner": owner,
        "claimant": claimant, "claimant_two": claimant_two, "staff": staff,
    }


def item(domain, **overrides):
    values = {
        "owner": domain["owner"], "kind": Item.Kind.FOUND, "category": domain["category"],
        "title": "黑色耳机", "description": "图书馆拾到黑色耳机", "occurred_at": timezone.now(),
        "location": domain["location"], "station": domain["station"],
        "location_detail": "三楼东侧座位", "latitude": 30.123456, "longitude": 120.123456,
        "review_status": Item.ReviewStatus.APPROVED, "business_status": Item.BusinessStatus.OPEN,
        "published_revision": 1,
    }
    values.update(overrides)
    return Item.objects.create(**values)


def lost_item(domain, owner):
    return item(domain, owner=owner, kind=Item.Kind.LOST, station=None, title="遗失黑色耳机")


@pytest.mark.django_db
def test_public_api_hides_sensitive_location_fields(domain):
    found = item(domain)
    response = APIClient().get(f"/api/v1/items/{found.pk}/")
    assert response.status_code == 200
    assert response.data["data"]["location_name"] == "图书馆"
    assert "location_detail" not in response.data["data"]
    assert "latitude" not in response.data["data"]
    assert "longitude" not in response.data["data"]


@pytest.mark.django_db
def test_mine_filter_returns_only_authenticated_owners_items(domain):
    own_draft = item(domain, kind=Item.Kind.LOST, review_status=Item.ReviewStatus.DRAFT, published_revision=None)
    other_owner = User.objects.create_user("other-owner", password="SafePassword!1", display_name="其他发布者")
    item(domain, owner=other_owner, kind=Item.Kind.LOST)
    client = APIClient()
    client.force_authenticate(domain["owner"])
    response = client.get("/api/v1/items/?kind=LOST&mine=true")
    assert response.status_code == 200
    assert [entry["id"] for entry in response.data["data"]["items"]] == [str(own_draft.pk)]
    anonymous = APIClient().get("/api/v1/items/?kind=LOST&mine=true")
    assert anonymous.status_code == 200
    assert anonymous.data["data"]["items"] == []


@pytest.mark.django_db
def test_registration_cannot_self_assign_admin_role():
    response = APIClient().post(
        "/api/v1/auth/register/",
        {"username": "new-student", "display_name": "新同学", "email": "new@example.test", "password": "SafePassword!2026", "role": "ADMIN"},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["data"]["role"] == User.Role.USER
    assert User.objects.get(username="new-student").role == User.Role.USER


@pytest.mark.django_db
def test_registration_uses_username_as_the_only_name_field():
    response = APIClient().post(
        "/api/v1/auth/register/",
        {"username": "single-name", "email": "single@example.test", "password": "SafePassword!2026"},
        format="json",
    )
    assert response.status_code == 201
    assert User.objects.get(username="single-name").display_name == "single-name"


@pytest.mark.django_db
def test_staff_cannot_review_item_outside_station_scope(domain):
    pending = item(
        domain,
        review_status=Item.ReviewStatus.PENDING,
        station=domain["other_station"],
        location=domain["other_location"],
        published_revision=None,
    )
    ItemRevision.objects.create(item=pending, revision=1, snapshot={"title": pending.title}, created_by=domain["owner"])
    with pytest.raises(PermissionDenied):
        review_item(pending, domain["staff"], approve=True, note="越权尝试")


@pytest.mark.django_db(transaction=True)
def test_one_found_item_can_only_have_one_active_reservation(domain):
    found = item(domain)
    first = submit_claim(found, domain["claimant"], "第一份申请", {"feature": "划痕"}, lost_item(domain, domain["claimant"]))
    second = submit_claim(found, domain["claimant_two"], "第二份申请", {"feature": "贴纸"}, lost_item(domain, domain["claimant_two"]))
    decide_claim(first, domain["staff"], "APPROVE", "证据通过")
    with pytest.raises(ValidationError):
        decide_claim(second, domain["staff"], "APPROVE", "不应通过")
    assert ActiveReservation.objects.filter(found_item=found).count() == 1
    found.refresh_from_db()
    assert found.business_status == Item.BusinessStatus.RESERVED


@pytest.mark.django_db(transaction=True)
def test_handover_needs_valid_code_and_two_sided_confirmation(domain):
    found = item(domain)
    claim = submit_claim(found, domain["claimant"], "可现场解锁", {"feature": "左侧划痕"}, lost_item(domain, domain["claimant"]))
    decide_claim(claim, domain["staff"], "APPROVE", "证据通过")
    claim.refresh_from_db()
    appointment, code = schedule_handover(claim, domain["claimant"], domain["station"], timezone.now() + timedelta(hours=1))
    assert appointment.code_digest != code
    verify_handover_code(claim, domain["claimant"], code)
    confirm_handover(claim, domain["claimant"])
    claim.refresh_from_db()
    assert claim.status == Claim.Status.HANDOVER_PENDING
    assert not ReturnRecord.objects.filter(claim=claim).exists()
    confirm_handover(claim, domain["staff"])
    claim.refresh_from_db(); found.refresh_from_db()
    assert claim.status == Claim.Status.COMPLETED
    assert found.business_status == Item.BusinessStatus.RETURNED
    assert ReturnRecord.objects.filter(claim=claim).count() == 1
    assert not ActiveReservation.objects.filter(claim=claim).exists()
    # 双方重复点击是幂等的，不得生成第二张归还记录。
    confirm_handover(claim, domain["claimant"])
    confirm_handover(claim, domain["staff"])
    assert ReturnRecord.objects.filter(claim=claim).count() == 1


@pytest.mark.django_db(transaction=True)
def test_handover_wrong_code_persists_five_attempt_lock(domain):
    found = item(domain)
    claim = submit_claim(found, domain["claimant"], "可现场核验", {"feature": "划痕"}, lost_item(domain, domain["claimant"]))
    decide_claim(claim, domain["staff"], "APPROVE", "证据通过")
    _, valid_code = schedule_handover(
        claim, domain["claimant"], domain["station"], timezone.now() + timedelta(hours=1)
    )
    for _ in range(5):
        with pytest.raises(ValidationError):
            verify_handover_code(claim, domain["claimant"], "000000" if valid_code != "000000" else "999999")
    appointment = claim.appointment
    appointment.refresh_from_db()
    assert appointment.failed_attempts == 5
    with pytest.raises(ValidationError, match="次数已达上限"):
        verify_handover_code(claim, domain["claimant"], valid_code)
    appointment.refresh_from_db()
    assert appointment.verified_at is None


@pytest.mark.django_db(transaction=True)
def test_handover_rejects_past_schedule_and_expired_code(domain):
    found = item(domain)
    claim = submit_claim(found, domain["claimant"], "可现场核验", {"feature": "贴纸"}, lost_item(domain, domain["claimant"]))
    decide_claim(claim, domain["staff"], "APPROVE", "证据通过")
    with pytest.raises(ValidationError, match="预约时间"):
        schedule_handover(claim, domain["claimant"], domain["station"], timezone.now() - timedelta(minutes=1))
    appointment, valid_code = schedule_handover(
        claim, domain["claimant"], domain["station"], timezone.now() + timedelta(hours=1)
    )
    appointment.code_expires_at = timezone.now() - timedelta(seconds=1)
    appointment.save(update_fields=["code_expires_at"])
    with pytest.raises(ValidationError, match="已过期"):
        verify_handover_code(claim, domain["claimant"], valid_code)


@pytest.mark.django_db(transaction=True)
def test_unstationed_item_supports_finder_review_and_direct_handover(domain):
    found = item(domain, station=None)
    claim = submit_claim(
        found,
        domain["claimant"],
        "耳机盒内侧有一处划痕",
        {"verification_detail": "耳机盒内侧有一处划痕"},
        lost_item(domain, domain["claimant"]),
    )
    decide_claim(claim, domain["owner"], "APPROVE", "特征相符")
    claim.refresh_from_db()
    assert claim.status == Claim.Status.APPROVED
    assert Conversation.objects.filter(claim=claim, participants__user=domain["owner"]).exists()
    assert Conversation.objects.filter(claim=claim, participants__user=domain["claimant"]).exists()

    start_direct_handover(claim, domain["claimant"])
    confirm_direct_handover(claim, domain["claimant"])
    claim.refresh_from_db()
    assert claim.status == Claim.Status.HANDOVER_PENDING
    confirm_direct_handover(claim, domain["owner"])
    claim.refresh_from_db(); found.refresh_from_db()
    assert claim.status == Claim.Status.COMPLETED
    assert found.business_status == Item.BusinessStatus.RETURNED
    assert ReturnRecord.objects.get(claim=claim).metadata["handover_method"] == Claim.HandoverMethod.DIRECT


@pytest.mark.django_db
def test_item_owner_can_close_open_item_with_audit(domain):
    found = item(domain)
    outsider = APIClient(); outsider.force_authenticate(domain["claimant"])
    assert outsider.post(f"/api/v1/items/{found.pk}/close/").status_code == 403
    owner = APIClient(); owner.force_authenticate(domain["owner"])
    response = owner.post(f"/api/v1/items/{found.pk}/close/")
    assert response.status_code == 200
    found.refresh_from_db()
    assert found.business_status == Item.BusinessStatus.CLOSED
    assert AuditLog.objects.filter(action="item.close", target_id=str(found.pk)).count() == 1
    assert owner.post(f"/api/v1/items/{found.pk}/close/").status_code == 400


@pytest.mark.django_db
def test_item_owner_can_withdraw_pending_item_and_edit_again(domain):
    pending = item(
        domain,
        kind=Item.Kind.LOST,
        review_status=Item.ReviewStatus.PENDING,
        published_revision=None,
    )
    outsider = APIClient(); outsider.force_authenticate(domain["claimant"])
    assert outsider.post(f"/api/v1/items/{pending.pk}/withdraw/").status_code == 404

    owner = APIClient(); owner.force_authenticate(domain["owner"])
    response = owner.post(f"/api/v1/items/{pending.pk}/withdraw/")
    assert response.status_code == 200
    assert response.data["data"]["review_status"] == Item.ReviewStatus.DRAFT
    assert set(response.data["data"]["allowed_actions"]) >= {"edit", "submit", "delete"}
    assert owner.patch(f"/api/v1/items/{pending.pk}/", {"title": "撤回后修订"}, format="json").status_code == 200
    assert AuditLog.objects.filter(action="item.withdraw", target_id=str(pending.pk)).count() == 1


@pytest.mark.django_db
def test_only_owner_can_delete_unpublished_draft(domain):
    draft = item(
        domain,
        review_status=Item.ReviewStatus.DRAFT,
        published_revision=None,
        approved_at=None,
    )
    outsider = APIClient(); outsider.force_authenticate(domain["claimant"])
    assert outsider.delete(f"/api/v1/items/{draft.pk}/").status_code == 404

    draft_id = str(draft.pk)
    owner = APIClient(); owner.force_authenticate(domain["owner"])
    assert owner.delete(f"/api/v1/items/{draft.pk}/").status_code == 204
    assert not Item.objects.filter(pk=draft.pk).exists()
    assert AuditLog.objects.filter(action="item.delete_draft", target_id=draft_id).count() == 1

    approved = item(domain)
    assert owner.delete(f"/api/v1/items/{approved.pk}/").status_code == 400
    assert Item.objects.filter(pk=approved.pk).exists()


@pytest.mark.django_db
def test_item_submit_reject_edit_resubmit_and_publish_revision(domain):
    draft = item(
        domain,
        kind=Item.Kind.LOST,
        review_status=Item.ReviewStatus.DRAFT,
        published_revision=None,
        approved_at=None,
        description="请加我微信后领取",
    )
    owner = APIClient(); owner.force_authenticate(domain["owner"])
    staff = APIClient(); staff.force_authenticate(domain["staff"])
    submit = owner.post(f"/api/v1/items/{draft.pk}/submit/")
    assert submit.status_code == 200
    draft.refresh_from_db()
    assert draft.review_status == Item.ReviewStatus.PENDING
    assert draft.revisions.count() == 1
    assert APIClient().get(f"/api/v1/items/{draft.pk}/").status_code == 404

    rejected = staff.post(
        f"/api/v1/items/{draft.pk}/review/", {"decision": "REJECT", "note": "请补充描述"}, format="json"
    )
    assert rejected.status_code == 200
    edited = owner.patch(f"/api/v1/items/{draft.pk}/", {"title": "修订后的黑色耳机"}, format="json")
    assert edited.status_code == 200
    assert owner.post(f"/api/v1/items/{draft.pk}/submit/").status_code == 200
    approved = staff.post(
        f"/api/v1/items/{draft.pk}/review/", {"decision": "APPROVE", "note": "信息完整"}, format="json"
    )
    assert approved.status_code == 200
    draft.refresh_from_db()
    assert draft.review_status == Item.ReviewStatus.APPROVED
    assert draft.published_revision == 2
    public = APIClient().get(f"/api/v1/items/{draft.pk}/")
    assert public.status_code == 200
    assert public.data["data"]["title"] == "修订后的黑色耳机"
    assert owner.patch(f"/api/v1/items/{draft.pk}/", {"title": "审核后不可覆盖"}, format="json").status_code == 400


@pytest.mark.django_db
def test_safe_item_submission_is_auto_approved_and_immediately_public(domain):
    draft = item(
        domain,
        kind=Item.Kind.FOUND,
        title="拾到黑色钥匙串",
        description="在图书馆一楼拾到一串黑色钥匙，现已送至服务站。",
        review_status=Item.ReviewStatus.DRAFT,
        published_revision=None,
        approved_at=None,
    )
    owner = APIClient(); owner.force_authenticate(domain["owner"])

    response = owner.post(f"/api/v1/items/{draft.pk}/submit/")

    assert response.status_code == 200
    assert response.data["data"]["review_status"] == Item.ReviewStatus.APPROVED
    draft.refresh_from_db()
    assert draft.published_revision == 1
    assert draft.approved_at is not None
    assert APIClient().get(f"/api/v1/items/{draft.pk}/").status_code == 200
    assert AuditLog.objects.filter(action="item.review.auto_approve", target_id=str(draft.pk)).exists()
