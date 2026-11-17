"""跨校区读取、写入与认领关联的隔离回归。"""
import pytest
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError
from apps.stations.models import School, Campus, CampusLocation, Station
from apps.items.models import Item, ItemCoordinateCandidate, ItemLocationCandidate
from apps.claims.services import submit_claim
from apps.matching.services import execute_match_run
from apps.matching.models import AlgorithmConfig
from apps.matching.engine import DEFAULT_WEIGHTS
from django.utils import timezone
from tests.test_portal_apis import portal, make_item

pytestmark = pytest.mark.mysql


@pytest.mark.django_db
def test_campus_scope_rejects_cross_campus_reads_and_writes(portal):
    school = School.objects.create(name="测试学校", code="scope-school")
    campus = Campus.objects.create(school=school, name="第二校区", code="scope-campus")
    location = CampusLocation.objects.create(campus=campus, name="另一图书馆", code="scope-library")
    foreign = make_item(portal, location=location, station=None)
    own = make_item(portal)
    client = APIClient(); client.force_authenticate(portal["owner"])
    assert client.get(f"/api/v1/items/{foreign.pk}/").status_code == 404
    client.credentials(HTTP_X_CAMPUS_ID=str(campus.pk))
    assert client.get(f"/api/v1/items/{foreign.pk}/").status_code == 200
    assert client.get(f"/api/v1/items/{own.pk}/").status_code == 404
    assert client.get("/api/v1/items/map-summary/").data["data"]["total"] == 1
    metadata = client.get("/api/v1/items/metadata/").data["data"]
    assert metadata["campus"] == {
        "id": campus.pk,
        "name": "第二校区",
        "school": "测试学校",
        "is_demo": False,
    }
    assert [entry["id"] for entry in metadata["locations"]] == [location.pk]
    payload = {"kind":"LOST", "category":portal["category"].pk, "title":"测试遗失", "description":"校区校验", "occurred_at":own.occurred_at.isoformat(), "location":portal["location"].pk}
    cross_campus_response = client.post("/api/v1/items/", payload, format="json")
    assert cross_campus_response.status_code == 400
    assert cross_campus_response.data["error"]["message"] == "地点不属于当前校区"
    payload["location"] = location.pk
    payload["station"] = portal["station"].pk
    assert client.post("/api/v1/items/", payload, format="json").status_code == 400
    client.credentials(HTTP_X_CAMPUS_ID="invalid")
    assert client.get("/api/v1/items/").status_code == 400


@pytest.mark.django_db
def test_item_creation_accepts_location_in_selected_campus(portal):
    """发布表单传入当前校区的地点时，应成功创建草稿。"""
    client = APIClient()
    client.force_authenticate(portal["owner"])
    client.credentials(HTTP_X_CAMPUS_ID=str(portal["location"].campus_id))
    payload = {
        "kind": "LOST",
        "category": portal["category"].pk,
        "title": "一串三把的钥匙",
        "description": "银色钥匙串，含三把钥匙和一枚蓝色挂件。",
        "occurred_at": timezone.now().isoformat(),
        "location": portal["location"].pk,
    }

    response = client.post("/api/v1/items/", payload, format="json")

    assert response.status_code == 201
    assert response.data["data"]["location"] == portal["location"].pk
    assert response.data["data"]["location_name"] == portal["location"].name


@pytest.mark.django_db
def test_protected_location_candidates_are_ranked_validated_and_not_public(portal):
    """遗失可保存多个可能地点，但公开线索不得泄露具体位置。"""
    first = CampusLocation.objects.create(
        campus=portal["location"].campus, name="逸夫图书馆", code="candidate-library", parent=portal["location"]
    )
    second = CampusLocation.objects.create(
        campus=portal["location"].campus, name="东操场", code="candidate-field", parent=portal["location"]
    )
    client = APIClient()
    client.force_authenticate(portal["owner"])
    payload = {
        "kind": "LOST",
        "category": portal["category"].pk,
        "title": "一串三把的钥匙",
        "description": "可能在图书馆到操场之间遗失。",
        "occurred_at": timezone.now().isoformat(),
        "location": portal["location"].pk,
        "location_candidate_ids": [first.pk, second.pk],
    }

    response = client.post("/api/v1/items/", payload, format="json")

    assert response.status_code == 201
    item = Item.objects.get(pk=response.data["data"]["id"])
    assert list(item.location_candidates.values_list("location_id", "rank")) == [
        (first.pk, 1),
        (second.pk, 2),
    ]
    assert [entry["name"] for entry in response.data["data"]["location_candidates"]] == [
        "逸夫图书馆",
        "东操场",
    ]

    item.review_status = Item.ReviewStatus.APPROVED
    item.published_revision = 1
    item.save(update_fields=["review_status", "published_revision"])
    public = APIClient().get(f"/api/v1/items/{item.pk}/")
    assert public.status_code == 200
    assert "location_candidates" not in public.data["data"]


@pytest.mark.django_db
def test_found_item_rejects_multiple_protected_locations(portal):
    first = CampusLocation.objects.create(
        campus=portal["location"].campus, name="第一教学楼", code="found-building-1", parent=portal["location"]
    )
    second = CampusLocation.objects.create(
        campus=portal["location"].campus, name="第二教学楼", code="found-building-2", parent=portal["location"]
    )
    client = APIClient()
    client.force_authenticate(portal["owner"])
    response = client.post(
        "/api/v1/items/",
        {
            "kind": "FOUND",
            "category": portal["category"].pk,
            "title": "拾到钥匙",
            "description": "教学楼拾到一串钥匙。",
            "occurred_at": timezone.now().isoformat(),
            "location": portal["location"].pk,
            "location_candidate_ids": [first.pk, second.pk],
        },
        format="json",
    )
    assert response.status_code == 400
    assert ItemLocationCandidate.objects.count() == 0


@pytest.mark.django_db
def test_real_map_coordinate_candidates_are_ranked_private_and_limited(portal):
    client = APIClient()
    client.force_authenticate(portal["owner"])
    payload = {
        "kind": "LOST",
        "category": portal["category"].pk,
        "title": "真实校园多地点测试",
        "description": "可能在工程坊或图书馆附近遗失。",
        "occurred_at": timezone.now().isoformat(),
        "location": portal["location"].pk,
        "location_candidate_points": [
            {"label": "工程坊", "latitude": 34.246007, "longitude": 108.981431, "coordinate_system": "GCJ02"},
            {"label": "钱学森图书馆", "latitude": 34.247100, "longitude": 108.984300, "coordinate_system": "GCJ02"},
        ],
    }

    response = client.post("/api/v1/items/", payload, format="json")

    assert response.status_code == 201
    item = Item.objects.get(pk=response.data["data"]["id"])
    assert list(item.coordinate_candidates.values_list("label", "rank")) == [("工程坊", 1), ("钱学森图书馆", 2)]
    assert response.data["data"]["coordinate_candidates"][1]["label"] == "钱学森图书馆"
    assert str(item.longitude) == "108.981431"

    item.review_status = Item.ReviewStatus.APPROVED
    item.published_revision = 1
    item.save(update_fields=["review_status", "published_revision"])
    public = APIClient().get(f"/api/v1/items/{item.pk}/")
    assert public.status_code == 200
    assert "coordinate_candidates" not in public.data["data"]
    assert "longitude" not in public.data["data"]

    payload["kind"] = "FOUND"
    rejected = client.post("/api/v1/items/", payload, format="json")
    assert rejected.status_code == 400
    assert ItemCoordinateCandidate.objects.filter(item__kind="FOUND").count() == 0


@pytest.mark.django_db
def test_claim_cannot_link_lost_item_from_another_campus(portal):
    school = School.objects.create(name="测试学校", code="claim-school")
    campus = Campus.objects.create(school=school, name="第二校区", code="claim-campus")
    location = CampusLocation.objects.create(campus=campus, name="教学区", code="claim-location")
    found = make_item(portal)
    lost = make_item(portal, location=location, station=None, kind=Item.Kind.LOST, owner=portal["member"])
    with pytest.raises(ValidationError, match="同一校区"):
        submit_claim(found, portal["member"], "测试", {}, lost)


@pytest.mark.django_db
def test_matching_index_contains_only_query_campus(portal):
    school = School.objects.create(name="匹配测试学校", code="match-school")
    campus = Campus.objects.create(school=school, name="第二校区", code="match-campus")
    location = CampusLocation.objects.create(campus=campus, name="图书馆", code="match-location")
    query = make_item(portal, kind=Item.Kind.LOST)
    local = make_item(portal, owner=portal["member"])
    same_owner = make_item(portal, title="同账号拾获线索")
    foreign = make_item(portal, location=location, station=None)
    AlgorithmConfig.objects.create(name="测试", version="scope-v1", weights=DEFAULT_WEIGHTS, thresholds={"min_coverage":0.6}, preprocessing={}, is_published=True, published_at=timezone.now(), created_by=portal["admin"])
    run = execute_match_run(query, portal["owner"])
    assert run.index_version.document_count == 1
    assert set(run.candidates.values_list("candidate_item_id", flat=True)) <= {local.pk}
    assert not run.candidates.filter(candidate_item=foreign).exists()
    assert not run.candidates.filter(candidate_item=same_owner).exists()
