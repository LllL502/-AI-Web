"""Resumable, budgeted prewarming using the same admission as live requests."""
from types import SimpleNamespace
from django.core.management.base import BaseCommand, CommandError
from rest_framework.response import Response
from apps.accounts.models import User
from apps.stations.models import Campus
from apps.assistant.runtime import managed_ai
from apps.assistant.tools import public_items_queryset
from apps.assistant.vector_index import load_vectors, build_vectors, model_key


class Command(BaseCommand):
    help = '按校区增量构建公开物品向量；重复运行可续建，不修改物品或认领'

    def add_arguments(self, parser):
        parser.add_argument('--owner', required=True, help='执行维护的现有管理员用户名')
        parser.add_argument('--campus-code', required=True)
        parser.add_argument('--kind', choices=['LOST', 'FOUND', 'ALL'], default='ALL')
        parser.add_argument('--limit', type=int, default=256)

    def handle(self, *args, **options):
        owner = User.objects.filter(username=options['owner'], role=User.Role.ADMIN, is_active=True).first()
        campus = Campus.objects.filter(code=options['campus_code'], is_active=True).first()
        if owner is None or campus is None:
            raise CommandError('请指定有效管理员和校区。')
        if not 1 <= options['limit'] <= 2000:
            raise CommandError('--limit须在1到2000之间。')
        request = SimpleNamespace(user=owner, headers={'X-Campus-ID': str(campus.pk)}, query_params={},
            FILES={}, data={'kind': options['kind'], 'limit': options['limit']}, path='/maintenance/assistant-index/')
        @managed_ai
        def execute(_, request):
            eligible = public_items_queryset(request)
            if options['kind'] != 'ALL':
                eligible = eligible.filter(kind=options['kind'])
            items = list(eligible.order_by('pk'))
            vectors, missing = load_vectors(items)
            saved = build_vectors(missing[:options['limit']], eligible)
            return Response({'data': {'eligible': len(items), 'already_current': len(vectors),
                'built': len(saved), 'remaining': max(0, len(missing)-len(saved)), 'model_key': model_key()}})
        try:
            result = execute(None, request)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(str(result.data['data']))
