"""物品实拍照片的安全处理与生命周期管理。

浏览器传来的文件名、扩展名、MIME 和 EXIF 都不可信。这里用 Pillow 解码真实
内容，再统一转为 WebP；重新编码会移除 GPS、拍摄设备等元数据，同时限制像素
与文件体积，避免超大图片耗尽服务端内存。
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Item, MediaAsset


MAX_MEDIA_PER_ITEM = 3
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_IMAGE_EDGE = 12_000
MAIN_MAX_SIZE = (2000, 2000)
THUMBNAIL_MAX_SIZE = (640, 640)
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}


@dataclass(frozen=True)
class ProcessedImage:
    digest: str
    width: int
    height: int
    main: bytes
    thumbnail: bytes


def _editable_item(item_id, actor) -> Item:
    item = Item.objects.select_for_update().get(pk=item_id)
    if item.owner_id != actor.id:
        raise PermissionDenied("只能管理自己发布信息的照片")
    if item.review_status not in {Item.ReviewStatus.DRAFT, Item.ReviewStatus.REJECTED}:
        raise ValidationError("只有草稿或被驳回的信息可以修改照片")
    return item


def _to_rgb(image: Image.Image) -> Image.Image:
    """在白底上展开透明通道，保证所有输入都能稳定编码成 RGB WebP。"""
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        background.alpha_composite(rgba)
        return background.convert("RGB")
    return image.convert("RGB")


def process_uploaded_image(upload) -> ProcessedImage:
    if upload.size > MAX_UPLOAD_BYTES:
        raise ValidationError({"files": ["单张照片不能超过 5MB。"]})
    raw = upload.read()
    if not raw:
        raise ValidationError({"files": ["照片内容为空。"]})

    try:
        with Image.open(BytesIO(raw)) as probe:
            image_format = (probe.format or "").upper()
            width, height = probe.size
            probe.verify()
        if image_format not in SUPPORTED_FORMATS:
            raise ValidationError({"files": ["仅支持 JPG、PNG 或 WebP 照片。"]})
        if width <= 0 or height <= 0 or width > MAX_IMAGE_EDGE or height > MAX_IMAGE_EDGE:
            raise ValidationError({"files": ["照片尺寸超出允许范围。"]})
        if width * height > MAX_IMAGE_PIXELS:
            raise ValidationError({"files": ["照片像素过大，请压缩后重新上传。"]})

        # verify() 会消耗解码器，因此重新打开；exif_transpose 修正手机旋转方向。
        with Image.open(BytesIO(raw)) as source:
            source.load()
            clean = _to_rgb(ImageOps.exif_transpose(source))
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValidationError({"files": ["文件不是有效照片，或图片数据已经损坏。"]}) from exc

    clean.thumbnail(MAIN_MAX_SIZE, Image.Resampling.LANCZOS)
    main_buffer = BytesIO()
    clean.save(main_buffer, format="WEBP", quality=86, method=6)

    thumbnail = clean.copy()
    thumbnail.thumbnail(THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)
    thumb_buffer = BytesIO()
    thumbnail.save(thumb_buffer, format="WEBP", quality=78, method=6)
    return ProcessedImage(
        digest=sha256(raw).hexdigest(),
        width=clean.width,
        height=clean.height,
        main=main_buffer.getvalue(),
        thumbnail=thumb_buffer.getvalue(),
    )


def upload_item_media(item_id, actor, uploads) -> list[MediaAsset]:
    uploads = list(uploads)
    if not uploads:
        raise ValidationError({"files": ["请选择需要上传的照片。"]})
    processed = [process_uploaded_image(upload) for upload in uploads]
    if len({image.digest for image in processed}) != len(processed):
        raise ValidationError({"files": ["本次选择中包含重复照片。"]})

    created: list[MediaAsset] = []
    try:
        with transaction.atomic():
            item = _editable_item(item_id, actor)
            existing = list(item.media.select_for_update().order_by("sort_order", "id"))
            if len(existing) + len(processed) > MAX_MEDIA_PER_ITEM:
                raise ValidationError({"files": [f"每条线索最多上传 {MAX_MEDIA_PER_ITEM} 张照片。"]})
            existing_hashes = {asset.sha256 for asset in existing}
            if any(image.digest in existing_hashes for image in processed):
                raise ValidationError({"files": ["这张照片已经上传过了。"]})

            next_order = max((asset.sort_order for asset in existing), default=-1) + 1
            for offset, image in enumerate(processed):
                stem = uuid4().hex
                asset = MediaAsset(
                    item=item,
                    sha256=image.digest,
                    width=image.width,
                    height=image.height,
                    sort_order=next_order + offset,
                    is_public=True,
                )
                asset.file.save(f"{stem}.webp", ContentFile(image.main), save=False)
                asset.thumbnail.save(f"{stem}.webp", ContentFile(image.thumbnail), save=False)
                asset.save()
                created.append(asset)
    except Exception:
        # 文件存储不参与数据库事务，失败时主动清理已经落盘的部分文件。
        for asset in created:
            if asset.file.name:
                asset.file.storage.delete(asset.file.name)
            if asset.thumbnail.name:
                asset.thumbnail.storage.delete(asset.thumbnail.name)
        raise
    return created


@transaction.atomic
def delete_item_media(item_id, media_id, actor) -> None:
    item = _editable_item(item_id, actor)
    try:
        asset = item.media.select_for_update().get(pk=media_id)
    except MediaAsset.DoesNotExist as exc:
        raise ValidationError("照片不存在或不属于当前线索") from exc
    file_name, thumb_name = asset.file.name, asset.thumbnail.name
    file_storage, thumb_storage = asset.file.storage, asset.thumbnail.storage
    asset.delete()
    transaction.on_commit(lambda: file_storage.delete(file_name) if file_name else None)
    transaction.on_commit(lambda: thumb_storage.delete(thumb_name) if thumb_name else None)


@transaction.atomic
def reorder_item_media(item_id, media_ids, actor) -> list[MediaAsset]:
    item = _editable_item(item_id, actor)
    assets = list(item.media.select_for_update().order_by("sort_order", "id"))
    try:
        ordered_ids = [int(value) for value in media_ids]
    except (TypeError, ValueError) as exc:
        raise ValidationError({"media_ids": ["照片顺序参数无效。"]}) from exc
    if len(ordered_ids) != len(set(ordered_ids)) or set(ordered_ids) != {asset.pk for asset in assets}:
        raise ValidationError({"media_ids": ["照片顺序必须完整包含当前线索的全部照片。"]})
    by_id = {asset.pk: asset for asset in assets}
    ordered = [by_id[media_id] for media_id in ordered_ids]
    for index, asset in enumerate(ordered):
        asset.sort_order = index
    MediaAsset.objects.bulk_update(ordered, ["sort_order"])
    return ordered
