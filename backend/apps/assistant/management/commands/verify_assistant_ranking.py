import json
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.assistant.tools import semantic_public_items
from apps.stations.models import Campus


class Command(BaseCommand):
    help = "使用本地向量模型比较纯语义与六因子重排，不修改演示记录"

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR).parent
        observation = json.loads((root / 'artifacts/local-ai-verification.json').read_text(encoding='utf-8'))['checks'][0]['observation']
        draft = dict(kind='LOST', title='寻找无线耳机及充电盒', category_hint='耳机', brand='',
            colors=['黑色'], occurred_at=None, location_hint='', public_description=observation)
        query = ' '.join([draft['title'], draft['category_hint'], '黑色', observation])
        campus = Campus.objects.get(code='demo-campus', school__is_demo=True)
        request = SimpleNamespace(headers={'X-Campus-ID': str(campus.pk)}, query_params={},
            build_absolute_uri=lambda value: 'http://127.0.0.1:8000' + value)
        before = semantic_public_items(request, kind='FOUND', query=query, limit=5)
        after = semantic_public_items(request, kind='FOUND', query=query, limit=5, draft=draft)
        passed = bool(after) and after[0]['color'] == '黑色' and '耳机' in after[0]['category']
        evidence = {'created_at': timezone.now().isoformat(), 'model': settings.AI_LOCAL_EMBEDDING_MODEL,
            'synthetic_demo_only': True, 'draft': draft, 'before': before, 'after': after, 'passed': passed}
        path = root / 'artifacts/assistant-reranking-verification.json'
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        for label, rows in [('before', before), ('after', after)]:
            for rank, row in enumerate(rows, 1):
                self.stdout.write(f"{label} #{rank}: {row['title']}")
        self.stdout.write(str(path))
        if not passed:
            raise CommandError('真实重排案例未通过，请查看证据。')
