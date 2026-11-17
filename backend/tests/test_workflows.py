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
    complete_station_pickup,
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
    lost = lost_item(domain, domain["claimant"])
    claim = submit_claim(found, domain["claimant"], "可现场解锁", {"feature": "左侧划痕"}, lost)
    decide_claim(claim, domain["staff"], "APPROVE", "证据通过")
    found.refresh_from_db(); lost.refresh_from_db()
    assert found.business_status == Item.BusinessStatus.RESERVED
    assert lost.business_status == Item.BusinessStatus.RESERVED
    public_ids = {
        row["id"] for row in APIClient().get("/api/v1/items/?page_size=100").data["data"]["items"]
    }
    assert str(found.pk) not in public_ids
    assert str(lost.pk) not in public_ids
    claim.refresh_from_db()
    appointment, code = schedule_handover(claim, domain["claimant"], domain["station"], timezone.now() + timedelta(hours=1))
    assert appointment.code_digest != code
    verify_handover_code(claim, domain["claimant"], code)
    confirm_handover(claim, domain["claimant"])
    claim.refresh_from_db()
    assert claim.status == Claim.Status.HANDOVER_PENDING
    assert not ReturnRecord.objects.filter(claim=claim).exists()
    confirm_handover(claim, domain["staff"])
    claim.refresh_from_db(); found.refresh_from_db(); lost.refresh_from_db()
    assert claim.status == Claim.Status.COMPLETED
    assert found.business_status == Item.BusinessStatus.RETURNED
    assert lost.business_status == Item.BusinessStatus.RETURNED
    assert ReturnRecord.objects.filter(claim=claim).count() == 1
    assert not ActiveReservation.objects.filter(claim=claim).exists()
    # 双方重复点击是幂等的，不得生成第二张归还记录。
    confirm_handover(claim, domain["claimant"])
    confirm_handover(claim, domain["staff"])
    assert ReturnRecord.objects.filter(claim=claim).count() == 1


@pytest.mark.django_db(transaction=True)
def test_station_custody_skips_station_selection_appointment_and_code(domain):
    domain["station"].approval_status = Station.ApprovalStatus.APPROVED
    domain["station"].save(update_fields=["approval_status"])
    found = item(domain)
    claim = submit_claim(
        found,
        domain["claimant"],
        "可现场核验",
        {"feature": "拉链内侧姓名缩写"},
        lost_item(domain, domain["claimant"]),
    )
    decide_claim(claim, domain["staff"], "APPROVE", "证据通过")

    client = APIClient()
    client.force_authenticate(domain["claimant"])
    detail = client.get(f"/api/v1/claims/{claim.pk}/")
    assert detail.status_code == 200
    assert detail.data["data"]["custody_station"]["name"] == domain["station"].name
    assert "schedule_handover" not in detail.data["data"]["allowed_actions"]
    assert "start_direct_handover" not in detail.data["data"]["allowed_actions"]
    assert "verify_code" not in detail.data["data"]["allowed_actions"]

    completed = complete_station_pickup(claim, domain["staff"])
    claim.refresh_from_db()
    assert completed.status == Claim.Status.COMPLETED
    assert claim.status == Claim.Status.COMPLETED
    assert claim.handover_method == Claim.HandoverMethod.STATION


@pytest.mark.django_db(transaction=True)
def test_claimant_can_remove_claim_from_own_list_without_destroying_record(domain):
    found = item(domain)
    claim = submit_claim(
        found,
        domain["claimant"],
        "可现场核验",
        {"feature": "耳机盒背面贴纸"},
        lost_item(domain, domain["claimant"]),
    )
    claimant_client = APIClient()
    claimant_client.force_authenticate(domain["claimant"])
    response = claimant_client.delete(f"/api/v1/claims/{claim.pk}/mine/")
    assert response.status_code == 204
    assert claimant_client.get(f"/api/v1/claims/{claim.pk}/").status_code == 404
    assert Claim.objects.filter(pk=claim.pk, claimant_deleted_at__isnull=False).exists()

    owner_client = APIClient()
    owner_client.force_authenticate(domain["owner"])
    assert owner_client.get(f"/api/v1/claims/{claim.pk}/").status_code == 200
    assert AuditLog.objects.filter(action="claim.hide_by_claimant", target_id=str(claim.pk)).exists()


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
    lost = lost_item(domain, domain["claimant"])
    claim = submit_claim(
        found,
        domain["claimant"],
        "耳机盒内侧有一处划痕",
        {"verification_detail": "耳机盒内侧有一处划痕"},
        lost,
    )
    decide_claim(claim, domain["owner"], "APPROVE", "特征相符")
    claim.refresh_from_db()
    lost.refresh_from_db()
    assert claim.status == Claim.Status.APPROVED
    assert lost.business_status == Item.BusinessStatus.RESERVED
    assert Conversation.objects.filter(claim=claim, participants__user=domain["owner"]).exists()
    assert Conversation.objects.filter(claim=claim, participants__user=domain["claimant"]).exists()

    start_direct_handover(claim, domain["claimant"])
    confirm_direct_handover(claim, domain["claimant"])
    claim.refresh_from_db()
    assert claim.status == Claim.Status.HANDOVER_PENDING
    confirm_direct_handover(claim, domain["owner"])
    claim.refresh_from_db(); found.refresh_from_db(); lost.refresh_from_db()
    assert claim.status == Claim.Status.COMPLETED
    assert found.business_status == Item.BusinessStatus.RETURNED
    assert lost.business_status == Item.BusinessStatus.RETURNED
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


@pytest.mark.django_db
def test_owner_can_edit_and_delete_open_publication_with_gallery_sync(domain):
    published = item(domain, kind=Item.Kind.LOST, station=None, title="公开的旧标题")
    owner = APIClient(); owner.force_authenticate(domain["owner"])
    outsider = APIClient(); outsider.force_authenticate(domain["claimant"])

    detail = owner.get(f"/api/v1/items/{published.pk}/")
    assert detail.status_code == 200
    assert set(detail.data["data"]["allowed_actions"]) >= {"edit", "delete", "close"}
    assert outsider.patch(
        f"/api/v1/items/{published.pk}/", {"title": "越权修改"}, format="json"
    ).status_code == 403

    edited = owner.patch(
        f"/api/v1/items/{published.pk}/", {"title": "广场同步的新标题"}, format="json"
    )
    assert edited.status_code == 200
    assert edited.data["data"]["title"] == "广场同步的新标题"
    published.refresh_from_db()
    assert published.review_status == Item.ReviewStatus.APPROVED
    assert published.revisions.filter(revision=published.published_revision).exists()
    assert AuditLog.objects.filter(action="item.update_published", target_id=str(published.pk)).count() == 1

    gallery = APIClient().get("/api/v1/items/?kind=LOST&page_size=100")
    gallery_rows = {entry["id"]: entry for entry in gallery.data["data"]["items"]}
    assert gallery_rows[str(published.pk)]["title"] == "广场同步的新标题"

    assert outsider.delete(f"/api/v1/items/{published.pk}/").status_code == 403
    assert owner.delete(f"/api/v1/items/{published.pk}/").status_code == 204
    assert not Item.objects.filter(pk=published.pk).exists()
    assert AuditLog.objects.filter(action="item.delete_published", target_id=str(published.pk)).count() == 1
    gallery_after_delete = APIClient().get("/api/v1/items/?kind=LOST&page_size=100")
    assert str(published.pk) not in {entry["id"] for entry in gallery_after_delete.data["data"]["items"]}


@pytest.mark.django_db
def test_admin_station_onboarding_requires_approval_and_supports_staff_permissions(domain):
    admin = User.objects.create_user(
        "platform-admin", password="SafePassword!2026", display_name="平台管理员", role=User.Role.ADMIN
    )
    client = APIClient(); client.force_authenticate(admin)
    created = client.post(
        "/api/v1/admin/stations/",
        {
            "name": "学生服务中心失物招领点", "location_id": domain["location"].pk,
            "address": "一楼综合服务台", "opening_hours": {"weekdays": "08:30-17:30"},
            "capacity": 80, "status": Station.Status.OPEN, "contact_phone": "0837-0000000",
            "latitude": "31.900000", "longitude": "102.220000", "coordinate_system": "GCJ02",
            "is_active": True,
        },
        format="json",
    )
    assert created.status_code == 201
    station_id = created.data["id"] if "id" in created.data else created.data["data"]["id"]
    assert not APIClient().get("/api/v1/stations/?page_size=100").data["data"]["items"]
    assert client.post(f"/api/v1/admin/stations/{station_id}/submit/").status_code == 200
    assert client.post(
        f"/api/v1/admin/stations/{station_id}/decision/", {"decision": "APPROVE"}, format="json"
    ).status_code == 200
    public_ids = {row["id"] for row in APIClient().get("/api/v1/stations/?page_size=100").data["data"]["items"]}
    assert station_id in public_ids
    assigned = client.post(
        f"/api/v1/admin/stations/{station_id}/members/",
        {"user_id": domain["staff"].pk, "can_review": True, "can_handover": False}, format="json",
    )
    assert assigned.status_code == 200
    membership = StationMembership.objects.get(station_id=station_id, user=domain["staff"])
    assert membership.can_review and not membership.can_handover


@pytest.mark.django_db
def test_published_item_with_claim_history_cannot_be_deleted(domain):
    published = item(domain)
    Claim.objects.create(
        found_item=published,
        claimant=domain["claimant"],
        statement="用于验证历史记录保护",
        status=Claim.Status.CANCELLED,
    )
    owner = APIClient(); owner.force_authenticate(domain["owner"])
    response = owner.delete(f"/api/v1/items/{published.pk}/")
    assert response.status_code == 400
    assert Item.objects.filter(pk=published.pk).exists()


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


@pytest.mark.django_db
def test_closed_lost_listing_with_claim_keeps_record_and_returns_clear_reason(domain):
 found=item(domain)
 lost=item(domain,kind=Item.Kind.LOST,owner=domain['claimant'],business_status=Item.BusinessStatus.CLOSED)
 claim=Claim.objects.create(found_item=found,related_lost_item=lost,claimant=domain['claimant'],statement='核验特征',status=Claim.Status.SUBMITTED)
 client=APIClient();client.force_authenticate(domain['claimant'])
 response=client.delete(f'/api/v1/items/{lost.pk}/')
 assert response.status_code==400
 assert '已关联认领申请，不能删除' in response.data['error']['message']
 assert response.data['error']['message']!='{}'
 lost.refresh_from_db();claim.refresh_from_db()
 assert lost.business_status==Item.BusinessStatus.CLOSED
 assert claim.status==Claim.Status.SUBMITTED
 mine=client.get('/api/v1/items/?mine=true&page_size=100').data['data']['items']
 assert str(lost.pk) in {row['id'] for row in mine}
