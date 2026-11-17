"""门户新增接口的权限与数据隔离回归测试。"""
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.administration.models import AuditLog
from apps.content.models import RecoveryStory
from apps.items.models import Category, Item, ItemRevision
from apps.messaging.models import Conversation, ConversationParticipant, Message
from apps.matching.engine import DEFAULT_WEIGHTS
from apps.matching.models import AlgorithmConfig, IndexVersion, MatchCandidate, MatchRun
from apps.notifications.models import Notification
from apps.stations.models import CampusLocation, Station, StationMembership

pytestmark = pytest.mark.mysql


@pytest.fixture
def portal(db):
    category = Category.objects.create(name="证件", code="portal-card")
    location = CampusLocation.objects.create(name="教学楼", code="portal-building")
    other_location = CampusLocation.objects.create(name="宿舍区", code="portal-dorm")
    station = Station.objects.create(
        name="教学楼服务站", code="portal-station", location=location, address="大厅"
    )
    other_station = Station.objects.create(
        name="宿舍服务站", code="portal-other-station", location=other_location, address="门卫处"
    )
    owner = User.objects.create_user("portal-owner", password="SafePassword!1", display_name="发布者")
    member = User.objects.create_user("portal-member", password="SafePassword!1", display_name="成员")
    outsider = User.objects.create_user("portal-outsider", password="SafePassword!1", display_name="局外人")
    staff = User.objects.create_user(
        "portal-staff", password="SafePassword!1", display_name="协调员", role=User.Role.STAFF
    )
    admin = User.objects.create_user(
        "portal-admin", password="SafePassword!1", display_name="管理员", role=User.Role.ADMIN
    )
    StationMembership.objects.create(user=staff, station=station, can_review=True, can_handover=True)
    return {
        "category": category,
        "location": location,
        "other_location": other_location,
        "station": station,
        "other_station": other_station,
        "owner": owner,
        "member": member,
        "outsider": outsider,
        "staff": staff,
        "admin": admin,
    }


def make_item(portal, **overrides):
    values = {
        "owner": portal["owner"],
        "kind": Item.Kind.FOUND,
        "category": portal["category"],
        "title": "蓝色校园卡",
        "description": "教学楼大厅拾到一张蓝色校园卡",
        "occurred_at": timezone.now() - timedelta(hours=1),
        "location": portal["location"],
        "station": portal["station"],
        "review_status": Item.ReviewStatus.APPROVED,
        "business_status": Item.BusinessStatus.OPEN,
        "published_revision": 1,
    }
    values.update(overrides)
    return Item.objects.create(**values)


@pytest.mark.django_db
def test_public_item_filter_accepts_root_category_and_includes_its_children(portal):
    root = Category.objects.create(name="证件卡片", code="filter-cards")
    portal["category"].parent = root
    portal["category"].save(update_fields=["parent"])
    other_root = Category.objects.create(name="学习用品", code="filter-study")
    other_leaf = Category.objects.create(name="书籍", code="filter-book", parent=other_root)
    expected = make_item(portal, title="应被一级类别筛选命中")
    make_item(portal, title="不应出现的其他类别", category=other_leaf)

    response = APIClient().get(f"/api/v1/items/?category={root.pk}")

    assert response.status_code == 200
    assert [entry["id"] for entry in response.data["data"]["items"]] == [str(expected.pk)]


@pytest.mark.django_db
def test_conversation_is_participant_scoped_and_can_post(portal):
    conversation = Conversation.objects.create(subject="认领沟通")
    ConversationParticipant.objects.create(conversation=conversation, user=portal["owner"])
    ConversationParticipant.objects.create(conversation=conversation, user=portal["member"])
    Message.objects.create(conversation=conversation, sender=portal["owner"], body="请说明卡套颜色")

    outsider = APIClient(); outsider.force_authenticate(portal["outsider"])
    assert outsider.get(f"/api/v1/messages/{conversation.pk}/").status_code == 404

    member = APIClient(); member.force_authenticate(portal["member"])
    response = member.post(
        f"/api/v1/messages/{conversation.pk}/messages/", {"body": "卡套是透明的"}, format="json"
    )
    assert response.status_code == 201
    assert response.data["data"]["body"] == "卡套是透明的"


@pytest.mark.django_db
def test_notifications_are_private_and_read_all_only_updates_owner(portal):
    own = Notification.objects.create(user=portal["member"], category="MATCH", title="新匹配", body="发现候选")
    other = Notification.objects.create(user=portal["outsider"], category="SYSTEM", title="其他", body="不可见")
    client = APIClient(); client.force_authenticate(portal["member"])
    response = client.get("/api/v1/notifications/")
    assert response.status_code == 200
    assert [entry["id"] for entry in response.data["data"]["items"]] == [own.pk]
    assert client.get(f"/api/v1/notifications/{other.pk}/").status_code == 404
    assert client.post("/api/v1/notifications/read-all/").data["data"]["updated"] == 1
    own.refresh_from_db(); other.refresh_from_db()
    assert own.read_at is not None and other.read_at is None


@pytest.mark.django_db
def test_favorite_rejects_another_users_private_draft(portal):
    private = make_item(
        portal, review_status=Item.ReviewStatus.DRAFT, published_revision=None, title="未公开卡片"
    )
    public = make_item(portal, title="公开卡片")
    client = APIClient(); client.force_authenticate(portal["member"])
    denied = client.post("/api/v1/items/favorites/", {"item_id": str(private.pk)}, format="json")
    accepted = client.post("/api/v1/items/favorites/", {"item_id": str(public.pk)}, format="json")
    assert denied.status_code == 400
    assert accepted.status_code == 201


@pytest.mark.django_db
def test_public_stories_require_publish_and_consent(portal):
    RecoveryStory.objects.create(
        title="已授权故事", slug="consented-story", body="物品已归还。", is_published=True,
        published_at=timezone.now(), consent_recorded=True, created_by=portal["admin"],
    )
    RecoveryStory.objects.create(
        title="未授权故事", slug="private-story", body="不得公开。", is_published=True,
        published_at=timezone.now(), consent_recorded=False, created_by=portal["admin"],
    )
    response = APIClient().get("/api/v1/content/stories/")
    assert response.status_code == 200
    assert [entry["slug"] for entry in response.data["data"]["items"]] == ["consented-story"]


@pytest.mark.django_db
def test_map_summary_counts_only_approved_public_items(portal):
    make_item(portal, kind=Item.Kind.LOST, title="公开遗失")
    make_item(portal, kind=Item.Kind.FOUND, title="公开招领")
    make_item(portal, kind=Item.Kind.LOST, title="未审核遗失", review_status=Item.ReviewStatus.PENDING, published_revision=None)
    all_response = APIClient().get("/api/v1/items/map-summary/")
    lost_response = APIClient().get("/api/v1/items/map-summary/?kind=LOST")
    assert all_response.status_code == 200
    assert all_response.data["data"]["total"] == 2
    assert lost_response.data["data"]["total"] == 1
    assert all_response.data["data"]["campus"]["is_demo"] is True
    assert all_response.data["data"]["kind_totals"] == {"LOST": 1, "FOUND": 1}
    assert {
        "id": portal["station"].pk,
        "name": "教学楼服务站",
        "status": "OPEN",
        "address": "大厅",
    } in all_response.data["data"]["stations"]
    location = next(entry for entry in all_response.data["data"]["locations"] if entry["id"] == portal["location"].pk)
    assert location["count"] == 2
    assert location["stations"] == [{
        "id": portal["station"].pk,
        "name": "教学楼服务站",
        "status": "OPEN",
        "address": "大厅",
    }]


@pytest.mark.django_db
def test_public_item_feed_uses_constant_query_count(portal, django_assert_max_num_queries):
    """学校、校区与媒体必须批量读取，列表长度增加时不能出现逐条查询。"""
    for index in range(6):
        make_item(portal, title=f"公开物品 {index}")
    with django_assert_max_num_queries(7):
        response = APIClient().get("/api/v1/items/?kind=FOUND")
    assert response.status_code == 200
    assert response.data["data"]["total"] == 6


@pytest.mark.django_db
def test_management_scope_and_admin_only_user_endpoint(portal):
    make_item(portal, review_status=Item.ReviewStatus.PENDING, published_revision=None)
    make_item(
        portal, location=portal["other_location"], station=portal["other_station"],
        review_status=Item.ReviewStatus.PENDING, published_revision=None,
    )
    staff = APIClient(); staff.force_authenticate(portal["staff"])
    overview = staff.get("/api/v1/admin/overview/")
    stations = staff.get("/api/v1/admin/stations/")
    assert overview.status_code == 200
    assert overview.data["data"]["pending_reviews"] == 1
    assert overview.data["data"]["stations"] == 1
    assert stations.data["data"]["total"] == 1
    assert staff.get("/api/v1/admin/users/").status_code == 403


@pytest.mark.django_db
def test_item_review_action_is_on_item_route(portal):
    pending = make_item(portal, review_status=Item.ReviewStatus.PENDING, published_revision=None)
    ItemRevision.objects.create(
        item=pending, revision=1, snapshot={"title": pending.title}, created_by=portal["owner"]
    )
    client = APIClient(); client.force_authenticate(portal["staff"])
    response = client.post(
        f"/api/v1/items/{pending.pk}/review/", {"decision": "APPROVE", "note": "信息完整"}, format="json"
    )
    assert response.status_code == 200
    pending.refresh_from_db()
    assert pending.review_status == Item.ReviewStatus.APPROVED
    assert client.post("/api/v1/items/subscriptions/999/review/", {"decision": "APPROVE"}).status_code == 404


@pytest.mark.django_db
def test_comparison_uses_persisted_snapshot_and_is_owner_scoped(portal):
    source = make_item(portal, owner=portal["member"], kind=Item.Kind.LOST, title="遗失校园卡")
    candidate_item = make_item(portal, title="拾到校园卡")
    config = AlgorithmConfig.objects.create(
        name="测试配置", version="portal-test-v1", weights=DEFAULT_WEIGHTS,
        thresholds={"min_coverage": 0.6}, preprocessing={}, is_published=True,
        created_by=portal["admin"], published_at=timezone.now(),
    )
    index = IndexVersion.objects.create(
        version="portal-index-v1", document_count=1, vocabulary_size=2,
        artifact_path="test:memory", corpus_checksum="a" * 64, config=config, is_active=True,
    )
    run = MatchRun.objects.create(
        query_item=source, requested_by=portal["member"], config=config, index_version=index,
        status=MatchRun.Status.COMPLETED, candidate_count=1,
    )
    MatchCandidate.objects.create(
        run=run, candidate_item=candidate_item, rank=1, raw_score=0.88, coverage=1,
        final_score=0.88,
        factors={
            "scores": {key: 1 for key in DEFAULT_WEIGHTS},
            "effective_weights": DEFAULT_WEIGHTS,
            "contributions": DEFAULT_WEIGHTS,
        },
        explanation={"level": "优先核查", "conflicts": [], "missing_factors": [], "text_terms": []},
        is_actionable=True,
    )
    path = f"/api/v1/matches/compare/?lost_id={source.pk}&found_id={candidate_item.pk}"
    owner_client = APIClient(); owner_client.force_authenticate(portal["member"])
    response = owner_client.get(path)
    assert response.status_code == 200
    assert response.data["data"]["run_id"] == run.pk
    assert response.data["data"]["factors"]["scores"]["text"] == 1
    outsider_client = APIClient(); outsider_client.force_authenticate(portal["outsider"])
    assert outsider_client.get(path).status_code == 404
    assert outsider_client.delete(f"/api/v1/matches/runs/{run.pk}/").status_code == 404
    assert owner_client.delete(f"/api/v1/matches/runs/{run.pk}/").status_code == 204
    assert not MatchRun.objects.filter(pk=run.pk).exists()
    assert AuditLog.objects.filter(action="matching.run.delete", target_id=str(run.pk)).exists()


@pytest.mark.django_db
def test_three_role_api_permission_matrix_and_suspended_login(portal):
    """用同一组端点验证匿名、普通用户、站点人员和管理员的角色边界。"""
    anonymous = APIClient()
    assert anonymous.get("/api/v1/items/").status_code == 200
    assert anonymous.get("/api/v1/notifications/").status_code == 403
    assert anonymous.get("/api/v1/admin/overview/").status_code == 403

    user = APIClient(); user.force_authenticate(portal["member"])
    for path in (
        "/api/v1/admin/overview/", "/api/v1/admin/users/", "/api/v1/admin/stations/",
        "/api/v1/admin/tasks/", "/api/v1/admin/matching-configs/",
    ):
        assert user.get(path).status_code == 403, path
    for path in (
        "/api/v1/messages/", "/api/v1/notifications/", "/api/v1/items/favorites/",
        "/api/v1/items/subscriptions/",
    ):
        assert user.get(path).status_code == 200, path

    staff = APIClient(); staff.force_authenticate(portal["staff"])
    assert staff.get("/api/v1/admin/overview/").status_code == 200
    station_response = staff.get("/api/v1/admin/stations/")
    assert station_response.status_code == 200
    assert station_response.data["data"]["total"] == 1
    for path in (
        "/api/v1/admin/users/", "/api/v1/admin/tasks/", "/api/v1/admin/matching-configs/",
    ):
        assert staff.get(path).status_code == 403, path

    admin = APIClient(); admin.force_authenticate(portal["admin"])
    for path in (
        "/api/v1/admin/overview/", "/api/v1/admin/users/", "/api/v1/admin/stations/",
        "/api/v1/admin/tasks/", "/api/v1/admin/matching-configs/",
    ):
        assert admin.get(path).status_code == 200, path

    portal["outsider"].account_status = User.Status.SUSPENDED
    portal["outsider"].save(update_fields=["account_status"])
    denied = anonymous.post(
        "/api/v1/auth/login/",
        {"username": portal["outsider"].username, "password": "SafePassword!1"},
        format="json",
    )
    assert denied.status_code == 400
    assert denied.data["error"]["code"] == "invalid_credentials"


@pytest.mark.django_db
def test_sensitive_item_fields_follow_owner_station_and_admin_scope(portal):
    """精确地点、坐标和审核意见只向所有者、所属站点人员或管理员开放。"""
    scoped_item = make_item(
        portal,
        location_detail="二楼东侧自习区 17 号座位",
        latitude="30.123456",
        longitude="120.654321",
        review_note="已核对公开描述",
    )
    out_of_scope_item = make_item(
        portal,
        location=portal["other_location"],
        station=portal["other_station"],
        title="宿舍区拾到校园卡",
        location_detail="三号楼门卫抽屉",
        latitude="30.223456",
        longitude="120.754321",
        review_note="由宿舍服务站审核",
    )
    sensitive_fields = {"location_detail", "latitude", "longitude", "review_note"}

    def detail(client, item):
        response = client.get(f"/api/v1/items/{item.pk}/")
        assert response.status_code == 200
        return response.data["data"]

    anonymous_data = detail(APIClient(), scoped_item)
    assert sensitive_fields.isdisjoint(anonymous_data)

    ordinary = APIClient(); ordinary.force_authenticate(portal["member"])
    assert sensitive_fields.isdisjoint(detail(ordinary, scoped_item))

    owner = APIClient(); owner.force_authenticate(portal["owner"])
    assert sensitive_fields.issubset(detail(owner, scoped_item))

    staff = APIClient(); staff.force_authenticate(portal["staff"])
    assert sensitive_fields.issubset(detail(staff, scoped_item))
    assert sensitive_fields.isdisjoint(detail(staff, out_of_scope_item))

    admin = APIClient(); admin.force_authenticate(portal["admin"])
    assert sensitive_fields.issubset(detail(admin, out_of_scope_item))


@pytest.mark.django_db
@override_settings(
    PUBLIC_TEST_MODE=True,
    PUBLIC_TEST_BLOCKED_USERNAMES={"portal-admin", "portal-staff", "portal-member"},
)
def test_public_test_blocks_documented_demo_accounts_but_allows_new_users(portal):
    """公网测试进程不能使用已公开的固定演示凭据，本地进程不受此开关影响。"""
    client = APIClient()
    for username in ("portal-admin", "portal-staff", "portal-member"):
        blocked = client.post(
            "/api/v1/auth/login/",
            {"username": username, "password": "SafePassword!1"},
            format="json",
        )
        assert blocked.status_code == 400
        assert blocked.data["error"]["code"] == "invalid_credentials"
    allowed = client.post(
        "/api/v1/auth/login/",
        {"username": "portal-outsider", "password": "SafePassword!1"},
        format="json",
    )
    assert allowed.status_code == 200
