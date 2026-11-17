"""物品实拍照片上传、隐私处理和所有权边界测试。"""

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.items.models import Category, Item, MediaAsset
from apps.stations.models import Campus, CampusLocation, School

pytestmark = [pytest.mark.mysql, pytest.mark.django_db]


@pytest.fixture
def media_domain():
    school = School.objects.create(name="照片测试大学", code="media-school")
    campus = Campus.objects.create(school=school, name="主校区", code="media-campus")
    location = CampusLocation.objects.create(campus=campus, name="图书馆", code="media-library")
    category = Category.objects.create(name="钥匙", code="media-key")
    owner = User.objects.create_user("media-owner", password="SafePassword!1", display_name="发布者")
    outsider = User.objects.create_user("media-outsider", password="SafePassword!1", display_name="其他用户")
    item = Item.objects.create(
        owner=owner,
        kind=Item.Kind.LOST,
        category=category,
        title="银色钥匙串",
        description="三把钥匙和一个蓝色挂件",
        occurred_at=timezone.now(),
        location=location,
    )
    return {"campus": campus, "owner": owner, "outsider": outsider, "item": item}


def image_upload(name="photo.jpg", color=(40, 90, 140), size=(1200, 900)):
    buffer = BytesIO()
    image = Image.new("RGB", size, color)
    exif = Image.Exif()
    exif[0x010F] = "Private Camera"
    exif[0x010E] = "GPS-like private note"
    image.save(buffer, format="JPEG", quality=92, exif=exif)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def campus_header(domain):
    return {"HTTP_X_CAMPUS_ID": str(domain["campus"].pk)}


def test_upload_reencodes_strips_metadata_and_exposes_cover(settings, tmp_path, media_domain):
    settings.MEDIA_ROOT = tmp_path
    client = client_for(media_domain["owner"])
    item = media_domain["item"]

    response = client.post(
        f"/api/v1/items/{item.pk}/media/",
        {"files": [image_upload()]},
        format="multipart",
        **campus_header(media_domain),
    )

    assert response.status_code == 201
    assert len(response.data["data"]["created"]) == 1
    asset = MediaAsset.objects.get(item=item)
    assert asset.file.name.endswith(".webp")
    assert asset.thumbnail.name.endswith(".webp")
    with Image.open(asset.file.path) as saved:
        assert saved.format == "WEBP"
        assert not saved.getexif()
        assert max(saved.size) <= 2000
    with Image.open(asset.thumbnail.path) as thumbnail:
        assert max(thumbnail.size) <= 640

    detail = client.get(f"/api/v1/items/{item.pk}/", **campus_header(media_domain)).data["data"]
    assert detail["image_url"].startswith("http://testserver/media/")
    assert len(detail["media"]) == 1


def test_media_reorder_delete_limit_and_owner_scope(settings, tmp_path, media_domain):
    settings.MEDIA_ROOT = tmp_path
    item = media_domain["item"]
    owner = client_for(media_domain["owner"])
    upload = owner.post(
        f"/api/v1/items/{item.pk}/media/",
        {"files": [image_upload("one.jpg", (10, 20, 30)), image_upload("two.jpg", (80, 90, 100))]},
        format="multipart",
        **campus_header(media_domain),
    )
    ids = [entry["id"] for entry in upload.data["data"]["created"]]

    reordered = owner.patch(
        f"/api/v1/items/{item.pk}/media-order/",
        {"media_ids": list(reversed(ids))},
        format="json",
        **campus_header(media_domain),
    )
    assert reordered.status_code == 200
    assert [entry["id"] for entry in reordered.data["data"]["media"]] == list(reversed(ids))

    third = owner.post(
        f"/api/v1/items/{item.pk}/media/",
        {"files": [image_upload("three.jpg", (120, 130, 140))]},
        format="multipart",
        **campus_header(media_domain),
    )
    assert third.status_code == 201
    too_many = owner.post(
        f"/api/v1/items/{item.pk}/media/",
        {"files": [image_upload("four.jpg", (160, 170, 180))]},
        format="multipart",
        **campus_header(media_domain),
    )
    assert too_many.status_code == 400
    assert "最多上传 3 张" in too_many.data["error"]["message"]

    outsider = client_for(media_domain["outsider"])
    denied = outsider.delete(
        f"/api/v1/items/{item.pk}/media/{ids[0]}/",
        **campus_header(media_domain),
    )
    assert denied.status_code == 404

    deleted = owner.delete(
        f"/api/v1/items/{item.pk}/media/{ids[0]}/",
        **campus_header(media_domain),
    )
    assert deleted.status_code == 204
    assert not MediaAsset.objects.filter(pk=ids[0]).exists()
