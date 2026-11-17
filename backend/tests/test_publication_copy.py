from tests.test_assistant_workflow import assistant_domain
from unittest.mock import patch
import pytest
from apps.assistant.publication import compose_public_draft,event_kind,confirmed_event_kind
from apps.assistant.providers import ProviderProtocolError,ProviderResult,extract_structured_description

def draft():
 return {'kind':'LOST','category_hint':'耳机','brand':'','colors':['黑色'],'location_hint':'田径场','occurred_at':None,'source_spans':{'category_hint':'耳机','colors':'黑色','location_hint':'田径场','occurred_at':'昨天晚上10点'},'uncertain_fields':[],'appearance_details':['充电盒盖有一道划痕','没有挂件']}

def test_fact_copy_does_not_publish_chat_wrappers_or_repeat_the_story():
 source='已填的物品描述：我昨天晚上10点在田径场丢了一副黑色耳机。补充：充电盒盖有一道划痕，没有挂件。帮我发布信息吧，好着急。'
 result=compose_public_draft(draft(),source)
 assert result['title']=='寻找黑色耳机'
 assert result['public_description']=='遗失物品：黑色耳机。充电盒盖有一道划痕；没有挂件。地点：田径场。时间：昨天晚上10点。'
 assert '补充' not in result['public_description']
 assert '着急' not in result['public_description']

def test_uncertainty_negation_and_private_features_are_not_promoted():
 source='不是苹果，可能是黑色耳机，可能在田径场。没有挂件，密码是1234。'
 d=draft();d.update(brand='苹果',appearance_details=['挂件','密码是1234']);d['source_spans'].pop('occurred_at')
 result=compose_public_draft(d,source)
 assert result['brand']==''
 assert result['title']=='寻找耳机'
 assert '可能为' in result['public_description']
 assert '可能地点' in result['public_description']
 assert '没有挂件' in result['public_description']
 assert '1234' not in result['public_description']

@pytest.mark.parametrize('source,expected',[('我昨天在田径场捡到黑色耳机','FOUND'),('我的耳机不见了','LOST'),('我捡到耳机，我的耳机不见了',None),('有人捡到我的耳机吗','LOST')])
def test_kind_is_resolved_or_queried_without_switching_a_question_to_found(source,expected):
 assert event_kind(source,'LOST')==expected

def test_explicit_clarification_is_recognised():
 assert confirmed_event_kind([{'role':'user','content':'是我捡到的。'}])=='FOUND'
 assert confirmed_event_kind([{'role':'user','content':'是我丢的。'}])=='LOST'

def test_invented_appearance_fact_is_rejected():
 source='黑色耳机，在田径场。'
 d=draft();d.update(appearance_details=['盒盖有星星贴纸']);d['source_spans'].pop('occurred_at')
 with patch('apps.assistant.providers.get_provider') as provider:
  provider.return_value.extract.return_value=ProviderResult(payload={'draft':{**d,'title':'','public_description':''},'follow_up_questions':[]},provider='test',model='test',simulated=False)
  with pytest.raises(ProviderProtocolError):extract_structured_description(source,'LOST')


def test_quoted_relative_time_is_kept_as_text_instead_of_an_invalid_datetime():
 source='昨天晚上10点多，在田径场捡到黑色耳机，没有挂件。'
 d=draft();d.update(kind='FOUND',occurred_at='昨天晚上10点多',appearance_details=['没有挂件']);d['source_spans']['occurred_at']='昨天晚上10点多'
 with patch('apps.assistant.providers.get_provider') as provider:
  provider.return_value.extract.return_value=ProviderResult(payload={'draft':{**d,'title':'','public_description':''},'follow_up_questions':[]},provider='test',model='test',simulated=False)
  result=extract_structured_description(source,'FOUND').payload['draft']
 assert result['occurred_at'] is None
 assert '昨天晚上10点多' in result['public_description']
 assert 'occurred_at' in result['uncertain_fields']


def test_kind_answer_keeps_prior_appearance_and_location():
 turns=[{'role':'user','content':'捡到耳机，我的耳机丢了'},{'role':'assistant','content':'这次是你捡到了别人的物品，还是你自己的物品丢了？'},{'role':'user','content':'我自己的耳机丢了'}]
 assert confirmed_event_kind(turns)=='LOST'

@pytest.mark.mysql
@pytest.mark.django_db(transaction=True)
def test_clarification_preserves_facts_and_unblocks_publication(assistant_domain, settings):
 settings.AI_PROVIDER_MODE="development_stub"
 settings.AI_LOCAL_EMBEDDING_URL=""
 settings.AI_LOCAL_EMBEDDING_MODEL=""
 from tests.test_assistant_workflow import authenticated_client
 client=authenticated_client(assistant_domain)
 first='我昨天在图书馆捡到黑色耳机。补充：我的黑色耳机丢了，盒盖有一道划痕。'
 ambiguous=client.post('/api/v1/assistant/conversation/',{'messages':[{'role':'user','content':first}]},format='json')
 assert ambiguous.status_code==200
 assert ambiguous.data['data']['stage']=='clarify_kind'
 history=[{'role':'user','content':first},{'role':'assistant','content':ambiguous.data['data']['reply']},{'role':'user','content':'我自己的耳机丢了'}]
 with patch('apps.assistant.views.converse',return_value={'description':'我自己的耳机丢了','reply':'','evidence':[]}):
  clarified=client.post('/api/v1/assistant/conversation/',{'messages':history},format='json')
 assert clarified.status_code==200
 pub=clarified.data['data']['publication']
 assert pub['kind']=='LOST'
 assert '黑色' in pub['description'] and '划痕' in pub['description'] and '图书馆' in pub['description']


def test_server_uses_source_time_instead_of_the_models_reference_timestamp():
 from apps.assistant.publication import resolve_time_evidence
 from django.utils import timezone
 from datetime import timedelta
 assert resolve_time_evidence('昨天晚上10点').date()==timezone.localtime().date()-timedelta(days=1)
 assert resolve_time_evidence('昨天晚上10点').hour==22
 assert resolve_time_evidence('昨天晚上10点多') is None
 assert resolve_time_evidence('晚上10点') is None


def test_chat_extraction_drops_only_unverified_slots_not_the_entire_reply():
 source='我丢了蓝色耳机，盒盖有划痕。'
 raw={'kind':'LOST','category_hint':'耳机','brand':'虚构品牌','colors':['蓝色'],'location_hint':'不存在的地点','occurred_at':None,'appearance_details':['盒盖有划痕','有星星贴纸'],'source_spans':{'colors':['蓝色']},'uncertain_fields':['unknown-private-field']}
 with patch('apps.assistant.providers.get_provider') as provider:
  provider.return_value.extract.return_value=ProviderResult(payload={'draft':raw},provider='test',model='test',simulated=False)
  result=extract_structured_description(source,'LOST',tolerant=True).payload['draft']
 assert result['category_hint']=='耳机'
 assert result['colors']==['蓝色']
 assert result['brand']=='' and result['location_hint']==''
 assert result['appearance_details']==['盒盖有划痕']
 assert '星星' not in result['public_description']


@pytest.mark.parametrize('phrase',['昨天晚上','昨晚','今天下午','2026年11月16日晚上'])
def test_time_only_phrase_is_never_a_location(phrase):
 d=draft();d.update(location_hint=phrase,appearance_details=[]);d['source_spans']={'location_hint':phrase}
 result=compose_public_draft(d,phrase+'丢了黑色耳机')
 assert result['location_hint']==''
 assert '地点：' not in result['public_description']
 assert result['source_spans']['occurred_at']==phrase

def test_relative_day_prefills_date_without_inventing_clock():
 from apps.assistant.publication import date_evidence,resolve_time_evidence
 from django.utils import timezone
 from datetime import timedelta
 assert date_evidence('我昨天晚上丢了蓝色笔袋')==(timezone.localtime().date()-timedelta(days=1)).isoformat()
 assert resolve_time_evidence('昨天晚上') is None
 assert date_evidence('2026年2月30日')==''
 assert date_evidence('不知道哪天')==''
 assert date_evidence('不是昨天，是今天')==timezone.localtime().date().isoformat()

@pytest.mark.parametrize('text',['帮我发布招领信息','我捡到一个蓝色笔袋','登记一条失物招领'])
def test_found_publication_intent_sets_found_kind(text):
 assert event_kind(text,'LOST')=='FOUND'


def test_followup_clock_uses_previously_stated_day_and_chinese_half_hour():
 from apps.assistant.publication import resolve_time_evidence
 value=resolve_time_evidence('晚上九点半','2026-11-16')
 assert value.isoformat()=='2026-11-16T21:30:00+08:00'
 assert resolve_time_evidence('九点半') is None
 assert resolve_time_evidence('大概晚上九点','2026-11-16') is None
