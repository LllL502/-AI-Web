from django.core.management.base import BaseCommand

from apps.items.models import Item
from apps.items.services import auto_review_pending_item


class Command(BaseCommand):
    help = "用当前后端自动审核规则处理升级前的用户待审线索"

    def handle(self, *args, **options):
        # 固定演示数据中特意保留了待审状态样例，不应被补审命令改写。
        pending_ids = list(
            Item.objects.filter(review_status=Item.ReviewStatus.PENDING, is_demo=False)
            .order_by("submitted_at", "created_at")
            .values_list("pk", flat=True)
        )
        approved = 0
        retained = 0
        for item_id in pending_ids:
            item = auto_review_pending_item(Item.objects.get(pk=item_id))
            if item.review_status == Item.ReviewStatus.APPROVED:
                approved += 1
            else:
                retained += 1
        self.stdout.write(self.style.SUCCESS(f"自动通过 {approved} 条，保留人工复核 {retained} 条。"))
