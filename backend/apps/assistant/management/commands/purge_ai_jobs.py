from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.assistant.models import AIJob


class Command(BaseCommand):
    help = '清理过期AI结果快照与7天前的终态任务，不清理业务物品或认领数据'

    def handle(self, *args, **options):
        now = timezone.now()
        cleared = AIJob.objects.filter(finished_at__lt=now-timedelta(seconds=settings.AI_RESULT_TTL_SECONDS), response__isnull=False).update(response=None)
        ids = list(AIJob.objects.exclude(status='RUNNING').filter(finished_at__lt=now-timedelta(days=7)).values_list('pk', flat=True)[:1000])
        deleted, _ = AIJob.objects.filter(pk__in=ids).delete()
        self.stdout.write(f'Expired result snapshots cleared: {cleared}; old jobs deleted: {deleted}')
