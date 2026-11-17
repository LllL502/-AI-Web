import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from rest_framework.response import Response
from apps.accounts.models import User
from apps.stations.models import Campus
from apps.assistant.benchmark import validate_dataset, eligible_candidates, candidate_text, query_text, evaluate_rankings, metrics
from apps.assistant.local_models import embeddings
from apps.assistant.ranking import PENALTIES, ACCEPTANCE_POLICY
from apps.matching.engine import DEFAULT_WEIGHTS
from apps.assistant.runtime import managed_ai, check_budget
from apps.assistant.vector_index import model_key


class Command(BaseCommand):
    help = '运行固定合成检索评测；不向物品库或物品向量索引写入评测记录'

    def add_arguments(self, parser):
        parser.add_argument('--owner', required=True)
        parser.add_argument('--dataset-version', choices=['v1', 'v2'], default='v2')
        parser.add_argument('--campus-code', default='demo-campus', help='仅用于维护任务归属，不向该校区导入评测数据')
        parser.add_argument('--split', choices=['development', 'validation', 'all'], default='development')

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR).parent
        path = root/f"data/benchmark/assistant-fixed-{options['dataset_version']}.json"
        raw = path.read_bytes()
        expected = path.with_suffix('.sha256').read_text(encoding='utf-8').strip()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise CommandError('固定数据集校验失败：如需修订标签，请创建新版本并保留旧版本。')
        dataset = json.loads(raw)
        validate_dataset(dataset)
        review_path = path.with_suffix('.review.json')
        review = json.loads(review_path.read_text(encoding='utf-8')) if review_path.exists() else {}
        if review and review.get('dataset_sha256') != expected:
            raise CommandError('人工复核记录与数据哈希不一致。')
        owner = User.objects.filter(username=options['owner'], role=User.Role.ADMIN, is_active=True).first()
        campus = Campus.objects.filter(code=options['campus_code'], is_active=True).first()
        if owner is None or campus is None:
            raise CommandError('请指定有效管理员和维护任务校区。')
        request = SimpleNamespace(user=owner, headers={'X-Campus-ID': str(campus.pk)}, query_params={},
            FILES={}, data={'split': options['split'], 'dataset_sha256': hashlib.sha256(raw).hexdigest()}, path='/maintenance/assistant-evaluation/')
        @managed_ai
        def run(_, request):
            started = time.monotonic()
            corpus = eligible_candidates(dataset)
            queries = [q for q in dataset['queries'] if options['split'] == 'all' or q['split'] == options['split']]
            vectors = []
            inputs = [candidate_text(row) for row in corpus] + [query_text(row) for row in queries]
            for offset in range(0, len(inputs), 16):
                check_budget()
                vectors.extend(embeddings(inputs[offset:offset+16]))
            encode_seconds = time.monotonic()-started
            rows = evaluate_rankings(dataset, queries, dict(zip([row['id'] for row in corpus], vectors[:len(corpus)])), vectors[len(corpus):])
            summary = {split: {method: metrics([r for r in rows if r['split'] == split], method)
                for method in ['keyword','semantic','semantic_six_factor','semantic_six_factor_gated']} for split in sorted({r['split'] for r in rows})}
            report = {'dataset_version': dataset['version'], 'dataset_sha256': hashlib.sha256(raw).hexdigest(),
                'created_at': timezone.now().isoformat(), 'synthetic_only': True,
                'label_review': review.get('status', dataset.get('review', {}).get('status', 'pending_human_review')),
                'review_record': review, 'acceptance_policy': ACCEPTANCE_POLICY,
                'embedding_model': settings.AI_LOCAL_EMBEDDING_MODEL, 'embedding_revision': settings.AI_LOCAL_EMBEDDING_REVISION,
                'model_key': model_key(), 'weights': DEFAULT_WEIGHTS, 'conflict_penalties': PENALTIES,
                'candidate_count': len(dataset['candidates']), 'eligible_candidate_count': len(corpus),
                'encoding_seconds': round(encode_seconds, 3), 'total_seconds': round(time.monotonic()-started, 3),
                'summary': summary, 'queries': rows}
            output = root/'artifacts/benchmark'/f"{dataset['version']}-{options['split']}.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            # Reports are versioned per run so later tuning does not erase evidence.
            stamp = timezone.now().strftime('%Y%m%dT%H%M%S%f')
            output = output.with_name(output.stem+'-'+stamp+'.json')
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            self.stdout.write(json.dumps(summary, ensure_ascii=True, indent=2))
            return Response({'data': {'report': str(output), 'dataset_sha256': report['dataset_sha256']}})
        try:
            result = run(None, request)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(str(result.data['data']))
