"""Short-lived, user/campus-bound dialogue memory; no chat database or client-trusted facts."""
import json
import re
from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.exceptions import ValidationError
from apps.stations.scope import selected_campus

SALT = 'xun-dialogue-v1'


def verified_workflow(request, context):
    from django.shortcuts import get_object_or_404
    from apps.claims.models import Claim
    from apps.items.models import Item
    result = {}
    campus = selected_campus(request)
    if context.get('claim_id'):
        from .agent_tools import own_claim
        claim = own_claim(request, context['claim_id'])
        result.update(claim_status=claim.status, handover_method=claim.handover_method,
            viewer_role='CLAIMANT' if claim.claimant_id==request.user.pk else 'FINDER' if claim.found_item.owner_id==request.user.pk else 'STAFF')
    if context.get('published_item_id'):
        item = get_object_or_404(Item, pk=context['published_item_id'], owner=request.user, location__campus_id=campus)
        result.update(publication_status=item.review_status, publication_title=item.title)
    if context.get('selected_item_id'):
        from .tools import public_items_queryset
        item = public_items_queryset(request).filter(pk=context['selected_item_id']).first()
        if item:
            result.update(selected_title=item.title, selected_kind=item.kind)
    return result


def read_memory(request, token):
    if not token:
        return {}
    try:
        data = signing.loads(token, salt=SALT, max_age=3600)
        if data['owner'] != request.user.pk or data['campus'] != selected_campus(request):
            raise ValueError()
        return data
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        raise ValidationError('这轮对话已过期或校区已变化，请点“新一轮”重新开始。') from None


def finish_turn(request, result, source, memory):
    from django.utils import timezone
    if len(source)>1800:
        source=result.get('description','')[:1800]
    state = {'owner': request.user.pk, 'campus': selected_campus(request),
        'reference_day': memory.get('reference_day', timezone.localdate().isoformat()),
        'event_day': memory.get('event_day', ''),
        'source': source, 'draft': result.get('draft', memory.get('draft')),
        'kind': result.get('publication', {}).get('kind', memory.get('kind', 'LOST')),
        'candidate_ids': [row['id'] for row in result.get('candidates', [])],
        'unavailable': result.get('unavailable_fields', memory.get('unavailable', [])),
        'last_question': result.get('question_field', 'none')}
    state = json.loads(json.dumps(state, cls=DjangoJSONEncoder))
    result['context_token'] = signing.dumps(state, salt=SALT, compress=True)
    return result


def unknown_fields(messages, memory):
    text = messages[-1]['content']
    result = set(memory.get('unavailable', []))
    unknown = r'不知道|不记得|记不清|不清楚|忘了|想不起来|没印象|没看清|记不得|不想说|不方便说'
    if re.search(unknown, text):
        for field, words in {'location':'哪里|哪儿|地点|位置|在哪', 'occurred_at':'几点|时间|哪天|什么时候',
                             'appearance':'颜色|外观|挂件|贴纸|样子|特征|卡套'}.items():
            if re.search(words, text):
                result.add(field)
        if re.fullmatch(r'(?:我)?(?:真的|也|确实)?(?:不知道|不记得|记不清|不清楚|忘了|想不起来)[了呀啊吧。！! ]*', text):
            if memory.get('last_question') not in {None, 'none'}:
                result.add(memory['last_question'])
    return sorted(result)


def guard_question(result, unavailable):
    """A forgotten field is a valid answer, never a reason to loop the question."""
    question = result.get('question_field', 'none')
    reply = result.get('reply', '')
    questions = ' '.join(re.findall(r'[^。！？?!\n]*[？?]', reply))
    if questions:
        if re.search(r'哪里|哪儿|地点|哪个地方|哪个位置|哪个校区|哪座楼|哪个楼|哪个区域|什么地方|哪个场所|在哪', questions):
            question = 'location'
        elif re.search(r'几点|什么时候|哪天|具体时间', questions):
            question = 'occurred_at'
    if question in unavailable:
        result['intent'] = 'search'
        result['question_field'] = 'none'
        result['reply'] = '记不清也没关系，不用猜。我们先用已经确定的信息找一找。'
    else:
        result['question_field'] = question
    result['unavailable_fields'] = unavailable
    return result


def ground_plan(result, messages, memory):
    """Keep tool use tied to the latest request, rather than inheriting an old search."""
    latest = messages[-1]['content']
    reply = result.get('reply','')
    help_question = re.search(r'能帮我做什么|能做什么|能帮我干什么|没有照片.*(?:可以|能).*发布|没照片.*(?:可以|能).*发布|怎么(?:发布|认领|交接)', latest)
    search_request = re.search(r'帮我找|帮我查|先找|先查|直接找|直接查|搜索|搜一下|查找|匹配一下|找找|查查', latest)
    publication_request = re.search(r'(?:帮我|请|准备|整理|登记).*(?:发布|寻物启事|招领信息)|(?:发布|登记)(?:一条|一下|寻物|招领)', latest)
    if re.search(r'(?:先别|不要|不想|先不|暂不|别).{0,4}发布',latest):
        result['intent']='chat';result['question_field']='none'
    elif help_question:
        result['intent']='chat';result['question_field']='none'
        # Do not tack an old data-collection question onto an answer about capabilities.
        result['reply']=re.sub(r'[^。！？?!\n]*[？?]', '', reply).strip() or '可以用文字发布，不一定需要照片。我可以帮你找线索、整理发布内容，再陪你办理认领和交接。'
    elif publication_request:
        result['intent']='publish';result['question_field']='none'
        if not re.search(r'草稿|发布|整理|登记|核对',reply):
            result['reply']='我先把现有线索整理成一份发布草稿，你核对后再提交。'
    elif search_request:
        result['intent']='search';result['question_field']='none'
        result['reply']=re.sub(r'[^。！？?!\n]*[？?]', '', reply).strip()
        last_reply=next((t['content'].split('\n\n')[0] for t in reversed(messages[:-1]) if t['role']=='assistant'),'')
        if not result['reply'] or result['reply']==last_reply or result['reply'] in last_reply:
            result['reply']='好，我直接按目前记得的线索查找。'
    return result
