"""Database admission, bounded request budgets and cooperative cancellation."""
import hashlib
import hmac
import json
import time
from contextvars import ContextVar
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from apps.stations.scope import selected_campus
from .models import AIAdmission, AIJob

current = ContextVar('assistant_runtime', default=None)


class AIBusy(APIException):
    status_code = 429
    default_code = 'ai_busy'
    default_detail = '当前请求较多，请稍后再试。'
    wait = 5


class AIConflict(APIException):
    status_code = 409
    default_code = 'ai_request_conflict'
    default_detail = '请求已在处理，或重复请求标识与内容不一致。'


class AIDeadline(APIException):
    status_code = 504
    default_code = 'ai_deadline_exceeded'
    default_detail = '本次处理已超时，请稍后重试。'


class AICancelled(APIException):
    status_code = 409
    default_code = 'ai_cancelled'
    default_detail = '本次任务已取消。'


def check_budget(default=60):
    state = current.get()
    if state is None:
        return default
    job_id, deadline = state
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AIDeadline()
    job = AIJob.objects.only('cancel_requested', 'status').get(pk=job_id)
    if job.cancel_requested:
        raise AICancelled()
    if job.status != 'RUNNING':
        raise AIDeadline()
    return max(.01, min(default, remaining))


def digest(value):
    return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def request_fingerprint(request):
    if len(request.FILES) > 1 or sum(upload.size for upload in request.FILES.values()) > 8 * 1024 * 1024:
        raise ValidationError('每次最多上传一张8MB以内的图片。')
    values = {}
    for key in sorted(request.data.keys()):
        if key in request.FILES:
            upload = request.FILES[key]
            if upload.size > 8 * 1024 * 1024:
                raise ValidationError({'image': '图片不能超过8MB。'})
            hasher = hashlib.sha256()
            for chunk in upload.chunks():
                hasher.update(chunk)
            upload.seek(0)
            values[key] = hasher.hexdigest()
        else:
            values[key] = request.data[key]
    return digest(json.dumps(values, sort_keys=True, ensure_ascii=False, default=str))


@transaction.atomic
def admit(request):
    campus = selected_campus(request)
    raw_key = request.headers.get('Idempotency-Key', '')
    if len(raw_key) > 128:
        raise ValidationError('重复请求标识不能超过128字符。')
    fingerprint = request_fingerprint(request)
    key = digest(raw_key) if raw_key else None
    AIAdmission.objects.get_or_create(pk=1)
    AIAdmission.objects.select_for_update().get(pk=1)
    now = timezone.now()
    AIJob.objects.filter(status='RUNNING', lease_until__lt=now).update(status='TIMED_OUT', finished_at=now, error_code='ai_deadline_exceeded')
    scope = AIJob.objects.filter(owner=request.user, campus_id=campus, action=request.path)
    if key:
        existing = scope.filter(idempotency_key=key).first()
        if existing:
            if existing.fingerprint != fingerprint:
                raise AIConflict('同一重复请求标识不能用于不同内容。')
            if existing.status == 'SUCCEEDED' and existing.finished_at and existing.finished_at > now-timedelta(seconds=settings.AI_RESULT_TTL_SECONDS):
                # Retrieval results are never replayed: public visibility can change.
                if existing.action.endswith(('/search/', '/conversation/', '/speech/')):
                    if existing.action.endswith('/speech/'):
                        raise AIConflict('语音不重复保存，请重新生成。')
                    raise AIConflict('检索结果可能变化，请使用新的请求标识重新检索。')
                return existing, True
            raise AIConflict({'detail': '请查询原任务状态；失败或过期任务重试需使用新标识。', 'workflow_id': str(existing.pk), 'status': existing.status})
    duplicate = scope.filter(fingerprint=fingerprint, status='RUNNING').first()
    if duplicate:
        raise AIConflict({'detail': '相同请求正在处理。', 'workflow_id': str(duplicate.pk)})
    recent = AIJob.objects.filter(owner=request.user, created_at__gte=now-timedelta(minutes=1))
    dialogue_paths = ('/api/v1/assistant/conversation/', '/api/v1/assistant/speech/')
    if request.path in dialogue_paths:
        recent = recent.filter(action=request.path)
        limit = getattr(settings, 'AI_CONVERSATION_REQUESTS_PER_MINUTE', 20) if request.path.endswith('/conversation/') else settings.AI_REQUESTS_PER_MINUTE
    else:
        recent = recent.exclude(action__in=dialogue_paths)
        limit = settings.AI_REQUESTS_PER_MINUTE
    if recent.count() >= limit:
        error = AIBusy('操作较频繁，请一分钟后再试。')
        error.wait = 60
        raise error
    if AIJob.objects.filter(status='RUNNING').count() >= settings.AI_MAX_CONCURRENT or AIJob.objects.filter(owner=request.user, status='RUNNING').exists():
        raise AIBusy()
    job = AIJob.objects.create(owner=request.user, campus_id=campus, action=request.path,
        fingerprint=fingerprint, idempotency_key=key,
        lease_until=now+timedelta(seconds=settings.AI_TOTAL_TIMEOUT_SECONDS+5))
    return job, False


def managed_ai(handler):
    @wraps(handler)
    def wrapped(self, request, *args, **kwargs):
        job, replay = admit(request)
        if replay:
            return Response(job.response, headers={'Idempotency-Replayed': 'true', 'X-AI-Job-ID': str(job.pk)})
        token = current.set((job.pk, time.monotonic()+settings.AI_TOTAL_TIMEOUT_SECONDS))
        try:
            result = handler(self, request, *args, **kwargs)
            check_budget()
            result.data.setdefault('data', {}).update(workflow_id=str(job.pk), status_url=f'/api/v1/assistant/jobs/{job.pk}/')
            payload = json.loads(json.dumps(result.data, cls=DjangoJSONEncoder))
            # A concurrent cancel must win over completion.
            with transaction.atomic():
                locked = AIJob.objects.select_for_update().get(pk=job.pk)
                if locked.cancel_requested:
                    raise AICancelled()
                if locked.status != 'RUNNING':
                    raise AIDeadline()
                locked.status = 'SUCCEEDED'
                locked.finished_at = timezone.now()
                # Search candidate snapshots are not retained or replayed.
                locked.response = None if request.path.endswith(('/search/', '/conversation/', '/speech/')) else payload
                locked.save(update_fields=['status','finished_at','response'])
            result['X-AI-Job-ID'] = str(job.pk)
            return result
        except Exception as exc:
            status = 'CANCELLED' if isinstance(exc, AICancelled) else 'TIMED_OUT' if isinstance(exc, AIDeadline) else 'FAILED'
            AIJob.objects.filter(pk=job.pk, status='RUNNING').update(status=status, finished_at=timezone.now(),
                error_code=getattr(exc, 'default_code', 'ai_internal_error'))
            if isinstance(exc, APIException):
                detail = exc.detail
                exc.detail = {**detail, 'workflow_id': str(job.pk)} if isinstance(detail, dict) else {'detail': detail, 'workflow_id': str(job.pk)}
            raise
        finally:
            current.reset(token)
    return wrapped
