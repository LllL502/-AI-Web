"""Attach matching synthetic assets without replacing any existing media."""
import hashlib
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image

from apps.items.models import Item, MediaAsset


class Command(BaseCommand):
    help = "仅给演示学校/演示校区的匹配演示记录补图，不覆盖已有图片"

    def handle(self, *args, **options):
        assets = Path(settings.BASE_DIR).parent / "data" / "demo-images"
        specs = [
            ("black-earbuds.png", "黑色", ("蓝牙耳机", "无线耳机充电盒")),
            ("black-umbrella.png", "黑色", ("折叠伞",)),
        ]
        count = 0
        for filename, color, names in specs:
            path = assets / filename
            if not path.exists():
                continue
            data = path.read_bytes()
            with Image.open(path) as image:
                width, height = image.size
            # The filenames do not assert a brand. Only generic matching appearances are attached.
            candidates = Item.objects.filter(is_demo=True,
                location__campus__code="demo-campus", location__campus__school__is_demo=True,
                color=color).order_by("pk")
            for item in candidates:
                if not any(name in item.description for name in names) or item.media.exists():
                    continue
                asset = MediaAsset(item=item, sha256=hashlib.sha256(data).hexdigest(),
                    width=width, height=height, sort_order=0, is_public=True)
                asset.file.save("synthetic-demo-" + filename, ContentFile(data), save=True)
                count += 1
                self.stdout.write(f"{item.pk} | {item.title} | {filename}")
        self.stdout.write(self.style.SUCCESS(f"新增 {count} 条演示配图；现有图片和业务字段均保留。"))
