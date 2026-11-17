"""Application-owned tools: the model cannot invent write permissions or IDs."""
import json
import re
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.crypto import salted_hmac
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from apps.items.models import Item, Category
from apps.items.serializers import ItemSerializer
from apps.items.services import submit_item
from apps.claims.models import Claim
from apps.claims.serializers import ClaimSerializer
from apps.claims.services import submit_claim, start_direct_handover, confirm_direct_handover, schedule_handover, supplement_claim, confirm_handover
from apps.stations.models import CampusLocation, Station
from apps.stations.scope import selected_campus
from .contracts import StrictSerializer
from .models import AgentActionReceipt
from .providers import extract_structured_description, ProviderProtocolError
from .publication import clean_source, event_kind, compose_public_draft, is_negated, date_evidence, resolve_time_evidence
from .dialogue_state import finish_turn
from .tools import semantic_public_items, query_public_items, public_items_queryset


def run_search(request, result, kind, excluded_ids, memory=None):
    memory = memory or {}
    action = result.get("intent", "auto")
    if action == "auto": action = "search"
    latest = result.pop("_latest_user", "")
    text = clean_source(result['description'])
    from django.utils import timezone
    day_pattern = r'\d{4}[年/.-]\d{1,2}[月/.-]\d{1,2}日?|今天|昨天|前天|昨晚|今晚|今早|昨早'
    if re.search(day_pattern, latest):
        event_day = date_evidence(latest)
    elif re.search(r'不知道|不记得|记不清|忘了', latest) and re.search(r'哪天|日期|哪一天|哪日', latest):
        event_day = ''
    elif 'event_day' in memory:
        event_day = memory['event_day']
    else:
        event_day = date_evidence(text, memory.get('reference_day'))
    memory = {**memory, 'event_day': event_day, 'reference_day': memory.get('reference_day', timezone.localdate().isoformat())}
    result['tool_trace'] = []
    detected = result.pop('_confirmed_kind', None) or event_kind(latest, None) or event_kind(text, (memory.get('draft') or {}).get('kind', kind))
    if detected is None:
        result.update(description='', reply='你提到了“捡到”和“丢失”。这次是你捡到了别人的物品，还是你自己的物品丢了？',
            candidates=[], stage='clarify_kind')
        return finish_turn(request, result, text, memory)
    kind = detected
    if not text.strip() and not memory.get('draft'):
        result.update(reply=result.get('reply') or '先告诉我丢失或拾到了什么物品，记得的外观也可以一起说。', candidates=[], stage='collecting')
        return finish_turn(request, result, text, memory)
    override = result.pop('_safe_draft',None)
    if override or (memory.get('draft') and memory['draft'].get('category_hint') and text == memory.get('source')):
        from .contracts import StructuredItemDraftSerializer
        parsed = StructuredItemDraftSerializer(data=override or memory['draft']); parsed.is_valid(raise_exception=True)
        draft = dict(parsed.validated_data)
    else:
        try:
            extracted = extract_structured_description(text, kind, tolerant=True)
            draft = extracted.payload['draft']
            result['extraction_provider'] = {'name':extracted.provider,'model':extracted.model,'simulated':extracted.simulated}
        except ProviderProtocolError:
            # Bad model formatting must not erase an otherwise valid dialogue.
            if memory.get('draft'):
                from .contracts import StructuredItemDraftSerializer
                parsed=StructuredItemDraftSerializer(data=memory['draft']);parsed.is_valid(raise_exception=True)
                draft=dict(parsed.validated_data)
                action='ask';result.update(intent='ask',question_field=result.get('question_field','none'))
                result['reply']=result.get('reply') or '我保留着之前的线索。你想先查找，还是继续补充外观？'
            else:
                result.update(description='',stage='collecting',candidates=[],reply=result.get('reply') or '我先帮你把线索理清。你记得物品最明显的特征是什么？')
                return finish_turn(request,result,text,memory)
    old = memory.get('draft') or {}
    if not draft['category_hint'] and old.get('category_hint') and old['category_hint'] in text and not is_negated(latest,old['category_hint']):
        draft['category_hint']=old['category_hint'];draft['source_spans']['category_hint']=old['category_hint']
    if not re.search(r'不是|没有|记错|说错|更正|其实|取消',latest):
        for field in ('brand','location_hint'):
            if not draft[field] and old.get(field) and old[field] in text:
                draft[field]=old[field];draft['source_spans'][field]=old[field]
        if not draft['colors']:
            draft['colors']=[value for value in old.get('colors',[]) if value in text]
            if draft['colors']:draft['source_spans']['colors']=draft['colors'][0]
        if not draft['appearance_details']:
            draft['appearance_details']=[value for value in old.get('appearance_details',[]) if value in text]
    from .identity_features import identity_markers
    if '卡' in draft['category_hint']:
        draft['identity_markers']=identity_markers(text)
    unavailable = set(result.get('unavailable_fields', memory.get('unavailable', [])))
    for field, value in [('location',draft['location_hint']),('occurred_at',draft['source_spans'].get('occurred_at',''))]:
        if value and value in latest and not re.search('不知道|不记得|记不清|不清楚|忘了', latest):
            unavailable.discard(field)
    if 'location' in unavailable:
        draft['location_hint']='';draft['source_spans'].pop('location_hint',None)
    if 'occurred_at' in unavailable:
        draft['occurred_at']=None;draft['source_spans'].pop('occurred_at',None)
    result['unavailable_fields']=sorted(unavailable)
    draft['kind'] = kind
    compose_public_draft(draft, text or memory.get('source',''))
    time_span = draft['source_spans'].get('occurred_at','')
    draft['occurred_at'] = resolve_time_evidence(time_span, event_day) if event_day and 'occurred_at' not in unavailable else None
    result['description'] = draft['public_description']
    result['draft'] = draft
    result['tool_trace'].append({'tool': 'extract_structured_description', 'status': 'completed'})
    if not draft['category_hint']:
        if not (draft['colors'] or draft['brand'] or draft['appearance_details'] or draft.get('identity_markers')):
            # A greeting or process question is not a usable item draft.
            result.pop('draft',None)
            result.update(description='',tool_trace=[],candidates=[],stage='dialogue')
            return finish_turn(request,result,text,{**memory,'draft':None})
        result.update(reply=result.get('reply') or '这些外观我记住了。它是什么物品，比如笔记本、耳机还是水杯？', candidates=[], stage='collecting')
        return finish_turn(request, result, text, memory)
    from django.conf import settings
    semantic = bool(settings.AI_LOCAL_EMBEDDING_URL and settings.AI_LOCAL_EMBEDDING_MODEL)
    opposite = 'FOUND' if kind == 'LOST' else 'LOST'
    query = ' '.join([draft['category_hint'], draft['public_description']])
    excluded = {str(i) for i in excluded_ids}
    if action == 'search':
        rows = semantic_public_items(request, kind=opposite, query=query, limit=10, draft=draft) if semantic else query_public_items(request, kind=opposite, query=query, limit=10)
        rows = [r for r in rows if r['id'] not in excluded][:5]
        summary = (f'这次查到{len(rows)}条可能相关的公开线索，可以先看看照片和外观。' if rows else '这次暂时没有足够匹配的公开线索。可以继续补充特征，或让我准备一条发布信息。')
        reply = result.get('reply','').strip()
        result.update(candidates=rows, stage='results', reply=(reply+'\n\n'+summary).strip())
        result['tool_trace'].append({'tool': 'semantic_public_items' if semantic else 'query_public_items', 'status': 'completed'})
    else:
        from .tools import _public_item_record
        eligible = {str(item.pk):item for item in public_items_queryset(request).filter(pk__in=memory.get('candidate_ids',[]),kind=opposite)}
        rows = [_public_item_record(request, eligible[key]) for key in memory.get('candidate_ids',[]) if key in eligible and key not in excluded]
        result.update(candidates=rows, stage='dialogue')
    index = result.pop('candidate_index',None)
    if action in {'select','exclude'}:
        if index and 1 <= index <= len(rows):
            if action == 'exclude':
                excluded_id=rows[index-1]['id'];rows.pop(index-1);result['excluded_id']=excluded_id
            else:
                result['ui_action']={'type':'select','index':index}
        else:
            result['reply']='先看看下方仍然有效的线索，告诉我是第几条，我再帮你展开。'
    elif action in {'publish','continue_claim'}:
        result['ui_action']={'type':action}
    categories = list(Category.objects.filter(is_active=True, children__isnull=True).values('id', 'name', 'synonyms'))
    locations = list(CampusLocation.objects.filter(campus_id=selected_campus(request), is_active=True).values('id', 'name', 'parent_id'))
    public_locations = [l for l in locations if l['parent_id'] is None]
    candidate_locations = [l for l in locations if l['parent_id'] is not None]
    hint = draft['category_hint']
    matches = [c['id'] for c in categories if c['name'] in hint or hint in c['name'] or hint in c['synonyms']]
    loc = [l['id'] for l in candidate_locations if draft['location_hint'] and (l['name'] == draft['location_hint'] or l['name'] in draft['location_hint'])]
    result['publication'] = {'kind': kind, 'title': draft['title'], 'description': draft['public_description'], 'brand': draft['brand'],
        'color': '、'.join(draft['colors']), 'category': matches[0] if len(matches) == 1 else '',
        'location': public_locations[0]['id'] if len(public_locations)==1 else '',
        'location_candidate_ids':loc[:5 if kind=='LOST' else 1], 'location_candidate_points':[],
        'occurred_date': event_day,
        'occurred_at': draft['occurred_at'].isoformat() if draft['occurred_at'] else ''}
    result['options'] = {'categories': categories, 'locations': public_locations, 'candidate_locations':candidate_locations}
    result['owned_lost'] = list(Item.objects.filter(owner=request.user, kind='LOST', review_status='APPROVED', business_status='OPEN', location__campus_id=selected_campus(request)).values('id', 'title', 'category_id'))
    # IDs used for claim selection always come from live, eligible database objects.
    by_id = {str(i.pk): i.category_id for i in public_items_queryset(request).filter(pk__in=[r['id'] for r in rows])}
    for row in rows:
        row['category_id'] = by_id.get(row['id'])
    return finish_turn(request, result, text, memory)


class AgentActionInput(StrictSerializer):
    action = serializers.ChoiceField(choices=['publish', 'claim', 'status', 'start_handover', 'confirm_handover', 'schedule', 'supplement', 'confirm_station_handover', 'decide', 'complete_station_pickup'])
    payload = serializers.JSONField()
    confirmed = serializers.BooleanField(default=False)
    key = serializers.UUIDField(required=False)


def own_claim(request, claim_id):
    # Reuse the website's existing claimant/finder/station/admin read scope.
    # Every write below is still checked by the corresponding domain service.
    from apps.claims.views import ClaimViewSet
    view = ClaimViewSet()
    view.request = request
    return get_object_or_404(view.get_queryset(), pk=claim_id)


def claim_data(request, claim):
    data = ClaimSerializer(claim, context={'request': request}).data
    # Do not duplicate private proof in agent receipts or chat summaries.
    fields = ['id','status','item_title','allowed_actions','conversation_id','custody_station','decision_note','appointment','viewer_role']
    return json.loads(json.dumps({k:data[k] for k in fields}, cls=DjangoJSONEncoder))


def execute_action(request, action, payload, confirmed=False, key=None, photos=None):
    from apps.items.storage_journal import atomic_media
    with atomic_media():
        return _execute_action(request, action, payload, confirmed, key, photos)


def _execute_action(request, action, payload, confirmed=False, key=None, photos=None):
    photos = photos or []
    if photos and (action != 'publish' or len(photos) > 3):
        raise ValidationError('发布最多附加三张照片。')
    allowed = {'publish': {'kind','title','description','category','location','occurred_at','brand','color','location_candidate_ids','location_candidate_points'},
        'claim': {'found_item_id','related_lost_item_id','statement'}, 'status': {'claim_id'},
        'start_handover': {'claim_id'}, 'confirm_handover': {'claim_id'}, 'schedule': {'claim_id','station_id','scheduled_at'}, 'supplement': {'claim_id','statement'}, 'confirm_station_handover': {'claim_id'}, 'decide': {'claim_id','decision','note'}, 'complete_station_pickup': {'claim_id'}}
    if not isinstance(payload, dict) or set(payload) - allowed[action]:
        raise ValidationError('工具参数不符合协议。')
    for field in (['found_item_id','related_lost_item_id'] if action == 'claim' else ['claim_id'] if action not in {'publish'} else []):
        serializers.UUIDField().run_validation(payload.get(field))
    if action in {'claim','supplement'}:
        serializers.CharField(min_length=5, max_length=3000).run_validation(payload.get('statement'))
    if action == 'schedule':
        serializers.IntegerField(min_value=1).run_validation(payload.get('station_id'))
    if action == 'decide':
        serializers.ChoiceField(choices=['APPROVE','REJECT','NEEDS_INFO']).run_validation(payload.get('decision'))
        serializers.CharField(min_length=2, max_length=1000).run_validation(payload.get('note'))
    if action == 'status':
        claim = own_claim(request, payload.get('claim_id'))
        return {'claim': claim_data(request, claim)}
    if not confirmed or key is None:
        raise ValidationError('请先确认本次操作。')
    fingerprint_data = [action, payload]
    if photos:
        from hashlib import sha256
        from apps.items.media import MAX_UPLOAD_BYTES
        hashes = []
        for photo in photos:
            if photo.size > MAX_UPLOAD_BYTES:
                raise ValidationError('单张照片不能超过5MB。')
            hashes.append(sha256(photo.read()).hexdigest())
            photo.seek(0)
        fingerprint_data.append(hashes)
    fingerprint = salted_hmac('agent-action', json.dumps(fingerprint_data, sort_keys=True, ensure_ascii=False)).hexdigest()
    receipt, _ = AgentActionReceipt.objects.get_or_create(owner=request.user, campus_id=selected_campus(request), key=key, defaults={'fingerprint': fingerprint})
    receipt = AgentActionReceipt.objects.select_for_update().get(pk=receipt.pk)
    if receipt.fingerprint != fingerprint:
        raise ValidationError('同一操作标识不能用于不同内容。')
    if receipt.result is not None:
        if 'claim' in receipt.result:
            return {**receipt.result, 'claim': claim_data(request, own_claim(request, receipt.result['claim']['id']))}
        return receipt.result
    if action == 'publish':
        serializer = ItemSerializer(data=payload, context={'request': request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save(owner=request.user, review_status=Item.ReviewStatus.DRAFT)
        if photos:
            from apps.items.media import upload_item_media
            upload_item_media(item.pk, request.user, photos)
        item = submit_item(item, request.user, request_id=getattr(request, 'request_id', ''))
        result = {'item': {'id': str(item.pk), 'title': item.title, 'category_id': item.category_id, 'review_status': item.review_status},
            'message': '信息已提交，审核状态以实际结果为准。'}
    elif action == 'claim':
        found = get_object_or_404(public_items_queryset(request), pk=payload.get('found_item_id'), kind='FOUND')
        related = get_object_or_404(Item, pk=payload.get('related_lost_item_id'), owner=request.user, location__campus_id=selected_campus(request))
        existing = Claim.objects.filter(found_item=found, claimant=request.user, related_lost_item=related, status__in=['SUBMITTED','NEEDS_INFO','APPROVED','HANDOVER_PENDING']).first()
        claim = existing or submit_claim(found, request.user, statement=str(payload.get('statement', '')).strip(), evidence={'verification_detail': str(payload.get('statement', '')).strip()}, related_lost_item=related)
        result = {'claim': claim_data(request, claim), 'message': '认领申请已提交，等待拾得者或服务站核验。'}
    else:
        claim = own_claim(request, payload.get('claim_id'))
        if action == 'supplement':
            claim = supplement_claim(claim, request.user, payload['statement'])
        elif action == 'decide':
            from apps.claims.services import decide_claim
            claim = decide_claim(claim, request.user, payload['decision'], payload['note'], getattr(request, 'request_id', ''))
        elif action == 'complete_station_pickup':
            from apps.claims.services import complete_station_pickup
            claim = complete_station_pickup(claim, request.user)
        elif action == 'start_handover':
            claim = start_direct_handover(claim, request.user)
        elif action == 'confirm_handover':
            claim = confirm_direct_handover(claim, request.user)
        elif action == 'confirm_station_handover':
            claim = confirm_handover(claim, request.user)
        elif action == 'schedule':
            date = serializers.DateTimeField().run_validation(payload.get('scheduled_at'))
            station = get_object_or_404(Station, pk=payload.get('station_id'), is_active=True, approval_status='APPROVED', status='OPEN', location__campus_id=selected_campus(request))
            appointment, code = schedule_handover(claim, request.user, station, date)
            claim.refresh_from_db()
            result = {'claim': claim_data(request, claim), 'one_time_code': code}
        if action != 'schedule':
            result = {'claim': claim_data(request, claim)}
    receipt.result = result
    receipt.save(update_fields=['result'])
    return result
