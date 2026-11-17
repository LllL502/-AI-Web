"""Identify old unreferenced media; deletion requires an explicit --apply."""
import time
import math
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from apps.items.models import MediaAsset


class Command(BaseCommand):
    help = '对账 items 下孤立文件；默认只报告，--apply 清理超过宽限期的文件。'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--grace-hours', type=float, default=24)

    def handle(self, *args, **options):
        if not math.isfinite(options['grace_hours']) or options['grace_hours'] < 1:
            raise CommandError('宽限期不得少于1小时。')
        root = Path(settings.MEDIA_ROOT).resolve()
        known = {name for pair in MediaAsset.objects.values_list('file', 'thumbnail') for name in pair if name}
        count = 0
        folder = root / 'items'
        for path in folder.rglob('*') if folder.exists() else []:
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
                continue
            name = path.relative_to(root).as_posix()
            if name in known or time.time() - path.stat().st_mtime < options['grace_hours'] * 3600:
                continue
            # Recheck immediately before deleting; recent in-flight uploads are excluded by grace.
            if MediaAsset.objects.filter(file=name).exists() or MediaAsset.objects.filter(thumbnail=name).exists():
                continue
            self.stdout.write(name)
            count += 1
            if options['apply']:
                path.unlink()
        self.stdout.write(f'{count} orphan file(s); apply={options["apply"]}')
