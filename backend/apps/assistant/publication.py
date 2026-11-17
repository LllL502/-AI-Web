"""Compose readable public copy from grounded fields, never from chat transcripts."""
import re
from datetime import datetime, timedelta
from django.utils import timezone
from django.utils.dateparse import parse_datetime

CHAT_LABELS = re.compile(r'(?:已填的物品描述|补充|图片外观（我已核对）)\s*[:：]')
UNCERTAIN = re.compile(r'可能|大概|好像|似乎|不确定|记不清|不太记得|也许|应该')
NEGATED = re.compile(r'(?:不是|并非|没有|不带|不含|不确定是不是|不确定是否是|没说.{0,4})(?:[的个一款副米浅深纯]|\s)*$')

TIME_ONLY = re.compile(r'^(?:今天|昨天|前天|昨晚|今晚|今早|昨早|\d{4}[年/.-]\d{1,2}[月/.-]\d{1,2}日?)?(?:凌晨|早上|上午|中午|下午|傍晚|晚上|晚间)?(?:(?:\d{1,2}|[零一二两三四五六七八九十]{1,3})(?:点|[:：])(?:(?:\d{1,2}|[零一二两三四五六七八九十]{1,3})分?)?(?:半|左右|多)?)?(?:的时候|时候)?$')


def date_evidence(source, reference_day=None):
    """Resolve the stated day independently; a day never invents a clock."""
    matches = list(re.finditer(r'\d{4}[年/.-]\d{1,2}[月/.-]\d{1,2}日?|今天|昨天|前天|昨晚|今晚|今早|昨早', source))
    if not matches:
        return ''
    match = matches[-1]
    left = max(source.rfind(mark, 0, match.start()) for mark in '，,。；;！？!?\n') + 1
    ends = [source.find(mark, match.end()) for mark in '，,。；;！？!?\n']
    right = min((pos for pos in ends if pos >= 0), default=len(source))
    clause = source[left:right]
    if UNCERTAIN.search(clause) or re.search(r'还是|或|要么|不是|并非|不在|不对|不记得|不知道|忘了', clause):
        return ''
    value = match[0]
    try:
        if value[0].isdigit():
            year, month, day = map(int, re.findall(r'\d+', value))
            return datetime(year, month, day).date().isoformat()
        offset = {'今天':0,'今晚':0,'今早':0,'昨天':1,'昨晚':1,'昨早':1,'前天':2}[value]
        day = datetime.strptime(reference_day, '%Y-%m-%d').date() if reference_day else timezone.localtime().date()
        return (day-timedelta(days=offset)).isoformat()
    except ValueError:
        return ''


def resolve_time_evidence(span, anchor_day=''):
    """Only parse explicit supported source text; never trust a model timestamp."""
    if re.search(r'可能|大概|左右|多|约|不确定|记不清|前后', span):
        return None
    try:
        value = parse_datetime(span)
    except ValueError:
        value = None
    if value:
        return value if timezone.is_aware(value) else timezone.make_aware(value)
    def chinese_number(match):
        value=match[0][:-1]
        digits={'零':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
        if '十' in value:
            left,right=value.split('十',1)
            number=digits.get(left,1)*10+digits.get(right,0)
        else:
            number=digits.get(value,0)
        return str(number)+match[0][-1]
    span=re.sub(r'[零一二两三四五六七八九十]{1,3}[点分]',chinese_number,span)
    clock = re.search(r'(\d{1,2})(?:点|[:：])(?:(\d{1,2})(?:分)?)?', span)
    if not clock:
        return None
    hour, minute = int(clock[1]), int(clock[2] or 0)
    if span[clock.end():].startswith('半'):
        minute=30
    if re.search(r'下午|晚上|傍晚|晚间|昨晚|今晚', span) and hour < 12:
        hour += 12
    elif re.search(r'凌晨|上午', span) and hour == 12:
        hour = 0
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    absolute = re.search(r'(\d{4})[年/.-](\d{1,2})[月/.-](\d{1,2})日?', span)
    try:
        if absolute:
            day = datetime(int(absolute[1]), int(absolute[2]), int(absolute[3])).date()
        else:
            relative = re.search(r'今天|昨天|前天|昨晚|今晚', span)
            if anchor_day:
                day = datetime.strptime(anchor_day,'%Y-%m-%d').date()
                return timezone.make_aware(datetime(day.year, day.month, day.day, hour, minute))
            if not relative:
                if not anchor_day:
                    return None
                day = datetime.strptime(anchor_day,'%Y-%m-%d').date()
            else:
                offset = {'今天':0, '今晚':0, '昨天':1, '昨晚':1, '前天':2}[relative[0]]
                day = timezone.localtime().date()-timedelta(days=offset)
        return timezone.make_aware(datetime(day.year, day.month, day.day, hour, minute))
    except ValueError:
        return None


def clean_source(text):
    return CHAT_LABELS.sub('', text).strip()


def context_clause(source, span):
    start = source.find(span)
    if start < 0:
        return ''
    left = max(source.rfind(mark, 0, start) for mark in '，,。；;！？!?\n') + 1
    ends = [source.find(mark, start+len(span)) for mark in '，,。；;！？!?\n']
    right = min((pos for pos in ends if pos >= 0), default=len(source))
    return source[left:right].strip()


def is_negated(source, value):
    positions = [m.start() for m in re.finditer(re.escape(value), source, re.I)]
    return bool(positions) and bool(NEGATED.search(source[max(0,positions[-1]-16):positions[-1]]))


def compose_public_draft(draft, source):
    location = draft.get('location_hint', '').strip(' ，,。')
    if location and TIME_ONLY.fullmatch(location):
        draft['location_hint'] = ''
        draft['source_spans'].pop('location_hint', None)
        draft['source_spans'].setdefault('occurred_at', location)
    uncertain = set(draft['uncertain_fields'])
    for field in ('brand', 'category_hint', 'location_hint'):
        if draft[field] and is_negated(source, draft[field]):
            draft[field] = ''
            uncertain.add(field)
    draft['colors'] = [value for value in draft['colors'] if not is_negated(source, value)]
    for field in ('brand', 'category_hint', 'colors', 'location_hint'):
        values = draft[field] if field == 'colors' else [draft[field]]
        if any(value and UNCERTAIN.search(context_clause(source, value)) for value in values):
            uncertain.add(field)
    draft['uncertain_fields'] = sorted(uncertain)
    category = draft['category_hint'] or '物品'
    qualifiers = [*draft['colors'], draft['brand']]
    known = [value for value in qualifiers if value and value not in category]
    def phrase(values):
        return re.sub(r'(?<=[\u4e00-\u9fff]) (?=[\u4e00-\u9fff])', '', ' '.join(dict.fromkeys(values)))
    subject = phrase([*known, category])
    title_parts = ([] if 'colors' in uncertain else draft['colors']) + ([] if 'brand' in uncertain else [draft['brand']])
    title_subject = phrase([value for value in title_parts if value and value not in category] + [category])
    draft['title'] = f"{'寻找' if draft['kind']=='LOST' else '拾到'}{title_subject}"[:80]
    appearance_uncertain = any(field in uncertain for field in ('colors', 'brand', 'category_hint'))
    parts = [f"{'遗失' if draft['kind']=='LOST' else '拾到'}物品：{'可能为' if appearance_uncertain else ''}{subject}。"]
    details = []
    for quote in draft.get('appearance_details', []):
        if quote not in source:
            raise ValueError('Ungrounded appearance detail')
        # Restore nearby negation/uncertainty if a model cuts off a qualifier.
        clause = context_clause(source, quote)
        detail = clause if UNCERTAIN.search(clause) or re.search(r'不是|没有|不带|并非', clause) else quote
        if re.search(r'手机号|证件号|邮箱|核验特征|私密|密码|学号|序列号|电话|解锁|帮我|补充[:：]|已填的物品描述', detail):
            continue
        detail = detail.strip(' ，,。；;\n')
        if re.search(r'丢|遗失|落在|不见|捡到|拾到',detail) and not re.search(r'划痕|磨损|破损|裂|贴纸|图案|挂件|打结|袋口|提手|拉链|里面|内有|封面|材质|尺寸',detail):
            continue  # Event narrative belongs to event slots, not appearance.
        if detail and detail not in details and detail not in subject:
            details.append(detail)
    if details:
        parts.append('；'.join(details)+'。')
    from .identity_features import identity_description
    identity = identity_description(draft.get('identity_markers',[]))
    if identity:
        parts.append(identity)
    location = draft['location_hint']
    if location:
        prefix = '可能地点' if 'location_hint' in uncertain else '地点'
        parts.append(f'{prefix}：{location}。')
    time_text = draft['source_spans'].get('occurred_at', '')
    if time_text and time_text in source:
        clause = context_clause(source, time_text)
        qualifier = '大约' if UNCERTAIN.search(clause) and not re.search(r'可能|大概|左右|大约|多|约', time_text) else ''
        parts.append(f'时间：{qualifier}{time_text}。')
    draft['public_description'] = ''.join(parts)
    return draft


def event_kind(text, default):
    """Recognise explicit user events, excluding questions about other finders."""
    found = lost = False
    for clause in re.split(r'[，,。；;！？!?\n]', clean_source(text)):
        if re.search(r'有人|谁|有没有|是否|如果|要是|听说|据说|别人|同学捡|朋友捡', clause):
            continue
        if re.search(r'(?<!没)(?<!没有)(?<!不是)(?:捡到|拾到|拾获|捡了)|(?:发布|登记|准备|整理).*(?:招领)', clause):
            found = True
        if re.search(r'(?<!没)(?<!没有)(?<!不是)(?:丢失|遗失|丢了|丢的|不见了|找不到了)', clause):
            lost = True
    if found and lost:
        return None
    return 'FOUND' if found else 'LOST' if lost else default


def confirmed_event_kind(messages):
    if len(messages) >= 2 and messages[-1]['role']=='user' and messages[-2]['role']=='assistant':
        if re.search(r'捡到.*还是.*丢', messages[-2]['content']):
            return event_kind(messages[-1]['content'], None)
    for turn in reversed(messages):
        if turn['role'] != 'user':
            continue
        text = turn['content'].strip(' ，,。！!\n')
        if re.fullmatch(r'(?:是)?(?:我)?(?:捡到|拾到|拾获)(?:的)?(?:，?不是我丢的)?', text):
            return 'FOUND'
        if re.fullmatch(r'(?:是)?(?:我)?(?:丢失|遗失|丢)(?:的|了)?(?:，?不是我捡到的)?', text):
            return 'LOST'
    return None
