import uuid

from django.conf import settings
from django.db import transaction
from django.utils.decorators import method_decorator
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .contracts import (
    AssistantExtractInputSerializer,
    AssistantSearchInputSerializer,
    PendingDraftInputSerializer,
)
from .providers import extract_structured_description, redact_sensitive_text
from .local_models import describe_image
from .runtime import managed_ai
from .models import AIJob
from .conversation import ConversationInput, converse
from .agent_tools import run_search, AgentActionInput, execute_action
from .tools import (
    TOOL_DEFINITIONS,
    generate_pending_draft,
    query_public_items,
    query_service_stations,
    semantic_public_items,
)


def _provider_capabilities():
    mode = settings.AI_PROVIDER_MODE
    return {
        "mode": mode,
        "simulated": mode == "development_stub",
        "configured": mode == "development_stub" or (
            mode == "openai_compatible"
            and bool(settings.AI_PROVIDER_BASE_URL and settings.AI_PROVIDER_API_KEY and settings.AI_PROVIDER_MODEL)
        ),
    }


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class AssistantConversationView(APIView):
    permission_classes = [IsAuthenticated]

    @managed_ai
    def post(self, request):
        serializer = ConversationInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        excluded = data.pop('excluded_ids')
        from .dialogue_state import read_memory, unknown_fields, guard_question, verified_workflow, ground_plan
        tool_context = data.pop('tool_context')
        memory = read_memory(request, data.pop('context_token'))
        unavailable = unknown_fields(data['messages'], memory)
        memory = {**memory, 'unavailable':unavailable, 'workflow':verified_workflow(request, tool_context)}
        first = data['messages'][0]['content']
        from .publication import event_kind, confirmed_event_kind
        latest_kind = event_kind(data['messages'][-1]['content'], None)
        data['kind'] = latest_kind or (memory.get('draft') or {}).get('kind', data['kind'])
        confirmed_kind = confirmed_event_kind(data['messages'])
        history_text = '\n'.join(t['content'] for t in data['messages'] if t['role']=='user')
        if not confirmed_kind and not latest_kind and event_kind(history_text, data['kind']) is None:
            return Response({'data': run_search(request, {'description': history_text}, data['kind'], excluded)})
        if confirmed_kind:
            # The answer already resolves the only pending question. Go
            # directly to grounded extraction instead of asking an extra model
            # to select evidence from a deliberately contradictory transcript.
            result = {'reply':'', 'description':redact_sensitive_text(history_text),
                'provider': {'name':'user_confirmed_event','model':'confirmed-input','simulated':False}}
        elif len(data['messages']) == 1 and first.startswith('图片外观（我已核对）：'):
            # The user already reviewed this observation in the chat. Do not
            # ask a second generative model to rewrite that confirmed source.
            safe = redact_sensitive_text(first)
            result = {'reply': '', 'description': safe, 'evidence': [{'message_index':0,'quote':safe}],
                      'provider': {'name':'user_confirmed_observation','model':'confirmed-input','simulated':False}}
        else:
            from .providers import ProviderProtocolError
            try:
                result = converse(**data, memory=memory)
            except ProviderProtocolError:
                from .conversation import natural_reply
                result = {'description':redact_sensitive_text(history_text), 'intent':'chat',
                    'facts_changed':True, 'question_field':'none',
                    'reply':natural_reply(data['messages'],memory)}
        if confirmed_kind:
            result['_confirmed_kind'] = confirmed_kind
            # A short "是我捡到的" resolves the event, not the already given
            # appearance, place and time. Keep that source for field extraction.
            result['description'] = history_text
        # A newly stated literal colour must not be lost if the planner marks
        # the mixed "blue, but I don't know where" answer as a non-fact turn.
        import re
        colors = re.findall(r'黑色|白色|蓝色|红色|绿色|黄色|粉色|紫色|灰色|银色|透明',data['messages'][-1]['content'])
        known_colors = memory.get('draft',{}).get('colors',[]) if memory.get('draft') else []
        if any(color not in known_colors for color in colors):
            result['facts_changed']=True
            if data['messages'][-1]['content'] not in result.get('description',''):
                result['description']=(result.get('description','')+'\n'+redact_sensitive_text(data['messages'][-1]['content'])).strip()
        if colors and result.get('intent')=='ask' and re.search(r'颜色|外观|样式',result.get('reply','')) and not re.search(r'贴纸|图案|挂件|划痕|磨损',result.get('reply','')):
            result['reply']=('地点先留空。' if 'location' in unavailable else '')+'、'.join(dict.fromkeys(colors))+'我记下了。物品上还有贴纸、图案或明显磨损吗？'
            result['question_field']='appearance'
        # Preserve validated memory when the user answers briefly or only says
        # that a detail is unknown. Later explicit corrections remain last.
        source = result.get('description','')
        if memory.get('source'):
            source = '\n'.join(dict.fromkeys((memory['source']+'\n'+source).splitlines()))
        result['description'] = source
        result['_latest_user'] = data['messages'][-1]['content']
        guard_question(result, unavailable)
        ground_plan(result, data['messages'], memory)
        return Response({'data': run_search(request, result, data['kind'], excluded, memory=memory)})


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class AssistantAgentActionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        photos = request.FILES.getlist('photos')
        if photos:
            import json
            from rest_framework.exceptions import ValidationError
            data = {key: request.data.get(key) for key in request.data if key != 'photos'}
            try:
                data['payload'] = json.loads(data.get('payload', '{}'))
            except (TypeError, ValueError):
                raise ValidationError('发布参数无效，请重试。')
        serializer = AgentActionInput(data=data)
        serializer.is_valid(raise_exception=True)
        return Response({'data': execute_action(request, **serializer.validated_data, photos=photos)})


class AssistantCapabilitiesView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "data": {
                    "provider": _provider_capabilities(),
                    "inputs": {"text": True, "image": bool(settings.AI_LOCAL_VISION_URL and settings.AI_LOCAL_VISION_MODEL)},
                    "semantic_retrieval": bool(settings.AI_LOCAL_EMBEDDING_URL and settings.AI_LOCAL_EMBEDDING_MODEL),
                    "tools": [
                        {
                            "name": definition.name,
                            "description": definition.description,
                            "read_only": definition.read_only,
                            "input_schema": definition.input_schema,
                        }
                        for definition in TOOL_DEFINITIONS
                    ],
                    "guardrails": [
                        "AI 不能批准认领、删除线索或完成交接。",
                        "候选只来自当前校区已公开的真实记录。",
                        "匹配排序不表示物品归属概率。",
                    ],
                }
            }
        )


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class AssistantPrepareView(APIView):
    permission_classes = [IsAuthenticated]

    @managed_ai
    def post(self, request):
        serializer = AssistantExtractInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = extract_structured_description(**serializer.validated_data)
        return Response(
            {
                "data": {
                    "workflow_id": str(uuid.uuid4()),
                    "provider": {
                        "name": result.provider,
                        "model": result.model,
                        "simulated": result.simulated,
                    },
                    "stages": [
                        {"id": "extract", "label": "结构化提取", "status": "completed"},
                        {"id": "confirm", "label": "用户确认", "status": "waiting"},
                        {"id": "retrieve", "label": "检索真实候选", "status": "blocked"},
                        {"id": "explain", "label": "证据解释", "status": "blocked"},
                    ],
                    **result.payload,
                }
            }
        )


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class AssistantSearchView(APIView):
    permission_classes = [IsAuthenticated]

    @managed_ai
    def post(self, request):
        serializer = AssistantSearchInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        draft = serializer.validated_data["draft"]
        query = " ".join(
            part
            for part in (
                draft["title"],
                draft["category_hint"],
                draft["brand"],
                " ".join(draft["colors"]),
                draft["public_description"],
            )
            if part
        )
        candidate_kind = "FOUND" if draft["kind"] == "LOST" else "LOST"
        semantic = bool(settings.AI_LOCAL_EMBEDDING_URL and settings.AI_LOCAL_EMBEDDING_MODEL)
        retrieve = semantic_public_items if semantic else query_public_items
        candidates = retrieve(
            request,
            kind=candidate_kind,
            query=query,
            limit=serializer.validated_data["limit"],
            **({"draft": draft} if semantic else {}),
        )
        stations = query_service_stations(request)
        return Response(
            {
                "data": {
                    "retrieval_method": "semantic_six_factor_v2" if semantic else "public_keyword_retrieval_v1",
                    "semantic_retrieval": semantic,
                    "message": (
                        "已从当前校区公开记录中取回真实候选。"
                        if candidates
                        else "暂未找到足够匹配的公开线索。"
                    ),
                    "candidates": candidates,
                    "citations": [
                        {"id": item["citation_id"], "item_id": item["id"], "url": item["url"]}
                        for item in candidates
                    ],
                    "stations": stations,
                    "tool_trace": [
                        {"tool": "query_public_items", "status": "completed", "read_only": True},
                        {"tool": "query_service_stations", "status": "completed", "read_only": True},
                    ],
                    "stages": [
                        {"id": "extract", "label": "结构化提取", "status": "completed"},
                        {"id": "confirm", "label": "用户确认", "status": "completed"},
                        {"id": "retrieve", "label": "检索真实候选", "status": "completed"},
                        {"id": "explain", "label": "证据解释", "status": "completed"},
                    ],
                }
            }
        )


class AssistantDraftPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PendingDraftInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = generate_pending_draft(request, item_payload=serializer.validated_data)
        return Response(
            {
                "data": {
                    **result,
                    "tool_trace": [
                        {"tool": "generate_pending_draft", "status": "completed", "read_only": True}
                    ],
                }
            }
        )


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class AssistantImageView(APIView):
    permission_classes = [IsAuthenticated]

    @managed_ai
    def post(self, request):
        from rest_framework.exceptions import ValidationError
        image = request.FILES.get("image")
        if image is None:
            raise ValidationError({"image": "请选择图片。"})
        observation = describe_image(image)
        return Response({"data": {"observation": observation,
            "model": settings.AI_LOCAL_VISION_MODEL, "requires_user_confirmation": True,
            "persisted": False, "message": "图片观察可能有误，请核对后再加入检索描述。"}})


class AssistantJobView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request, job_id):
        from django.shortcuts import get_object_or_404
        from apps.stations.scope import selected_campus
        return get_object_or_404(AIJob, pk=job_id, owner=request.user, campus_id=selected_campus(request))

    def get(self, request, job_id):
        job = self.get_object(request, job_id)
        from django.utils import timezone
        AIJob.objects.filter(pk=job.pk, status='RUNNING', lease_until__lt=timezone.now()).update(
            status='TIMED_OUT', finished_at=timezone.now(), error_code='ai_deadline_exceeded')
        job.refresh_from_db()
        return Response({'data': {'workflow_id': str(job.pk), 'status': job.status,
            'cancel_requested': job.cancel_requested, 'error_code': job.error_code,
            'created_at': job.created_at, 'finished_at': job.finished_at}})

    def post(self, request, job_id):
        job = self.get_object(request, job_id)
        AIJob.objects.filter(pk=job.pk, status='RUNNING').update(cancel_requested=True)
        job.refresh_from_db()
        return Response({'data': {'workflow_id': str(job.pk), 'status': job.status,
            'cancel_requested': job.cancel_requested}})


@method_decorator(transaction.non_atomic_requests, name='dispatch')
class AssistantSpeechView(APIView):
    permission_classes = [IsAuthenticated]

    @managed_ai
    def post(self, request):
        from .speech import SpeechInput, generate_speech
        serializer = SpeechInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({'data': generate_speech(serializer.validated_data['text'])},
            headers={'Cache-Control': 'no-store'})


class AssistantHealthView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .health import model_health
        return Response({'data': model_health()})


class AssistantJobLookupView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.shortcuts import get_object_or_404
        from apps.stations.scope import selected_campus
        from .runtime import digest
        from rest_framework.exceptions import ValidationError
        key = request.headers.get('Idempotency-Key', '')
        action = request.query_params.get('action', '')
        if not key or len(key) > 128 or action not in {
            '/api/v1/assistant/prepare/', '/api/v1/assistant/search/', '/api/v1/assistant/image/'}:
            raise ValidationError('请提供原请求的Idempotency-Key和action。')
        job = get_object_or_404(AIJob, owner=request.user, campus_id=selected_campus(request),
            action=action, idempotency_key=digest(key))
        return AssistantJobView().get(request, job.pk)

