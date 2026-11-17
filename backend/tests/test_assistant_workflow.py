from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.items.models import Category, Item
from apps.stations.models import Campus, CampusLocation, School, Station
from apps.assistant.providers import ProviderProtocolError, ProviderResult, extract_structured_description


pytestmark = pytest.mark.mysql


@pytest.mark.django_db(transaction=True)
def test_managed_ai_replays_only_identical_owner_requests(assistant_domain):
    from apps.assistant.models import AIJob
    client = authenticated_client(assistant_domain)
    result = ProviderResult(payload={'draft': structured_draft(), 'follow_up_questions': []}, provider='test', model='test', simulated=False)
    with patch('apps.assistant.views.extract_structured_description', return_value=result) as provider:
        first = client.post('/api/v1/assistant/prepare/', {'description': '黑色耳机丢在图书馆', 'kind': 'LOST'}, format='json', HTTP_IDEMPOTENCY_KEY='stable-key')
        repeated = client.post('/api/v1/assistant/prepare/', {'description': '黑色耳机丢在图书馆', 'kind': 'LOST'}, format='json', HTTP_IDEMPOTENCY_KEY='stable-key')
        conflict = client.post('/api/v1/assistant/prepare/', {'description': '另一副耳机丢失了', 'kind': 'LOST'}, format='json', HTTP_IDEMPOTENCY_KEY='stable-key')
    assert first.status_code == repeated.status_code == 200
    assert first.data == repeated.data
    assert repeated['Idempotency-Replayed'] == 'true'
    assert conflict.status_code == 409
    assert provider.call_count == 1
    job = AIJob.objects.get()
    assert job.status == 'SUCCEEDED'
    assert job.fingerprint != '黑色耳机丢在图书馆'
    other = User.objects.create_user('ai-other-owner', password='SafePassword!2026')
    client.force_authenticate(other)
    assert client.get(f'/api/v1/assistant/jobs/{job.pk}/').status_code == 404


@pytest.mark.django_db(transaction=True)
def test_running_job_can_be_found_and_cooperatively_cancelled(assistant_domain):
    from apps.assistant.models import AIJob
    client = authenticated_client(assistant_domain)
    def provider(**kwargs):
        lookup = client.get('/api/v1/assistant/jobs/?action=/api/v1/assistant/prepare/', HTTP_IDEMPOTENCY_KEY='cancel-me')
        assert lookup.status_code == 200
        job_id = lookup.data['data']['workflow_id']
        assert client.post(f'/api/v1/assistant/jobs/{job_id}/', {}, format='json').data['data']['cancel_requested'] is True
        return ProviderResult(payload={'draft': structured_draft(), 'follow_up_questions': []}, provider='test', model='test', simulated=False)
    with patch('apps.assistant.views.extract_structured_description', side_effect=provider):
        response = client.post('/api/v1/assistant/prepare/', {'description': '黑色耳机丢在图书馆'}, format='json', HTTP_IDEMPOTENCY_KEY='cancel-me')
    assert response.status_code == 409
    assert response.data['error']['code'] == 'ai_cancelled'
    assert AIJob.objects.get().status == 'CANCELLED'


@pytest.mark.django_db(transaction=True)
def test_server_deadline_does_not_commit_a_successful_result(assistant_domain):
    import time
    from apps.assistant.runtime import current
    from apps.assistant.models import AIJob
    def provider(**kwargs):
        job_id, _ = current.get()
        current.set((job_id, time.monotonic()-1))
        return ProviderResult(payload={'draft': structured_draft(), 'follow_up_questions': []}, provider='test', model='test', simulated=False)
    with patch('apps.assistant.views.extract_structured_description', side_effect=provider):
        response = authenticated_client(assistant_domain).post('/api/v1/assistant/prepare/', {'description': '黑色耳机丢在图书馆'}, format='json')
    assert response.status_code == 504
    assert AIJob.objects.get().status == 'TIMED_OUT'
    assert AIJob.objects.get().response is None


@pytest.mark.django_db(transaction=True)
def test_ai_rate_limit_is_enforced_before_provider_call(assistant_domain, settings):
    settings.AI_REQUESTS_PER_MINUTE = 1
    client = authenticated_client(assistant_domain)
    result = ProviderResult(payload={'draft': structured_draft(), 'follow_up_questions': []}, provider='test', model='test', simulated=False)
    with patch('apps.assistant.views.extract_structured_description', return_value=result) as provider:
        assert client.post('/api/v1/assistant/prepare/', {'description': '黑色耳机丢在图书馆'}, format='json').status_code == 200
        response = client.post('/api/v1/assistant/prepare/', {'description': '蓝色手机丢在食堂里'}, format='json')
    assert response.status_code == 429
    assert response['Retry-After'] == '60'
    assert provider.call_count == 1


@pytest.mark.django_db(transaction=True)
def test_global_admission_is_serialized_across_database_connections(assistant_domain, settings):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from types import SimpleNamespace
    from django.db import connections, close_old_connections
    from apps.assistant.models import AIAdmission, AIJob
    from apps.assistant.runtime import admit, AIBusy
    settings.AI_MAX_CONCURRENT = 1
    AIAdmission.objects.get_or_create(pk=1)
    second = User.objects.create_user('parallel-ai-user', password='SafePassword!2026')
    barrier = Barrier(2)
    def run(owner):
        close_old_connections()
        try:
            request = SimpleNamespace(user=owner, path='/api/v1/assistant/prepare/',
                headers={'X-Campus-ID': str(assistant_domain['campus'].pk)}, query_params={}, FILES={},
                data={'description': '黑色耳机丢失了'})
            barrier.wait(timeout=10)
            try:
                admit(request)
                return 'accepted'
            except AIBusy:
                return 'busy'
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [assistant_domain['owner'], second]))
    assert sorted(results) == ['accepted', 'busy']
    assert AIJob.objects.filter(status='RUNNING').count() == 1


@pytest.mark.django_db
def test_persistent_vectors_reuse_and_invalidate_on_content_or_revision(assistant_domain, settings):
    from apps.assistant.tools import semantic_public_items
    from apps.assistant.models import ItemVector
    from django.core.cache import cache
    settings.AI_LOCAL_EMBEDDING_URL = 'http://127.0.0.1:8082/v1'
    settings.AI_LOCAL_EMBEDDING_MODEL = 'persistent-test'
    item = make_item(assistant_domain)
    request = authenticated_client(assistant_domain).get('/api/v1/assistant/capabilities/').wsgi_request
    from rest_framework.request import Request
    request = Request(request)
    with patch('apps.assistant.local_models.embeddings', side_effect=lambda texts: [[1., 0.] for _ in texts]) as embed:
        semantic_public_items(request, kind='FOUND', query='耳机')
        assert embed.call_count == 2
        cache.clear()
        semantic_public_items(request, kind='FOUND', query='耳机')
        assert embed.call_count == 3  # only the query; no process cache required
        item.description = '编辑后的公开描述'
        item.save(update_fields=['description'])
        semantic_public_items(request, kind='FOUND', query='耳机')
        assert embed.call_count == 5
        settings.AI_LOCAL_EMBEDDING_REVISION = 'changed-weights'
        semantic_public_items(request, kind='FOUND', query='耳机')
        assert embed.call_count == 7
    assert ItemVector.objects.filter(item=item).count() == 2


@pytest.mark.django_db
def test_recheck_visibility_after_vector_inference(assistant_domain, settings):
    from apps.assistant.tools import semantic_public_items
    from rest_framework.request import Request
    settings.AI_LOCAL_EMBEDDING_URL = 'http://127.0.0.1:8082/v1'
    settings.AI_LOCAL_EMBEDDING_MODEL = 'withdrawal-test'
    item = make_item(assistant_domain)
    request = Request(authenticated_client(assistant_domain).get('/api/v1/assistant/capabilities/').wsgi_request)
    calls = 0
    def embed(texts):
        nonlocal calls
        calls += 1
        if calls == 2:
            Item.objects.filter(pk=item.pk).update(review_status=Item.ReviewStatus.PENDING)
        return [[1., 0.] for _ in texts]
    with patch('apps.assistant.local_models.embeddings', side_effect=embed):
        assert semantic_public_items(request, kind='FOUND', query='耳机') == []


@pytest.mark.django_db
def test_more_than_500_indexed_items_are_searchable_without_reembedding(assistant_domain, settings):
    from apps.assistant.tools import semantic_public_items
    from apps.assistant.models import ItemVector
    from apps.assistant.vector_index import content_hash, model_key, IndexPending
    from rest_framework.request import Request
    settings.AI_LOCAL_EMBEDDING_URL = 'http://127.0.0.1:8082/v1'
    settings.AI_LOCAL_EMBEDDING_MODEL = 'large-corpus-test'
    settings.AI_INDEX_SYNC_LIMIT = 0
    template = make_item(assistant_domain)
    items = [Item(id=__import__('uuid').uuid4(), owner=template.owner, category=template.category,
        location=template.location, title=f'公开耳机{i}', description='公开描述', kind='FOUND',
        occurred_at=template.occurred_at, review_status='APPROVED', business_status='OPEN') for i in range(501)]
    Item.objects.bulk_create(items)
    request = Request(authenticated_client(assistant_domain).get('/api/v1/assistant/capabilities/').wsgi_request)
    with patch('apps.assistant.local_models.embeddings') as embed:
        with pytest.raises(IndexPending):
            semantic_public_items(request, kind='FOUND', query='耳机')
        embed.assert_not_called()
    all_items = [template, *items]
    ItemVector.objects.bulk_create([ItemVector(item=item, model_key=model_key(), content_hash=content_hash(item),
        dimension=2, vector=[1., 0.] if item.pk == items[-1].pk else [0., 1.]) for item in all_items])
    with patch('apps.assistant.local_models.embeddings', return_value=[[1., 0.]]) as embed:
        result = semantic_public_items(request, kind='FOUND', query='耳机')
    assert result[0]['id'] == str(items[-1].pk)
    assert embed.call_count == 1


@pytest.mark.django_db
def test_edit_during_indexing_never_commits_the_old_vector(assistant_domain, settings):
    from apps.assistant.tools import semantic_public_items
    from apps.assistant.models import ItemVector
    from rest_framework.request import Request
    settings.AI_LOCAL_EMBEDDING_URL = 'http://127.0.0.1:8082/v1'
    settings.AI_LOCAL_EMBEDDING_MODEL = 'concurrent-edit-test'
    item = make_item(assistant_domain)
    request = Request(authenticated_client(assistant_domain).get('/api/v1/assistant/capabilities/').wsgi_request)
    calls = 0
    def embed(texts):
        nonlocal calls
        calls += 1
        if calls == 1:
            Item.objects.filter(pk=item.pk).update(description='已经修改的描述')
        return [[1., 0.] for _ in texts]
    with patch('apps.assistant.local_models.embeddings', side_effect=embed):
        assert semantic_public_items(request, kind='FOUND', query='耳机') == []
    assert not ItemVector.objects.filter(item=item).exists()


@pytest.fixture(autouse=True)
def isolate_inference_configuration(settings):
    # Unit/API contract tests must not depend on a developer's running model.
    settings.AI_PROVIDER_MODE = "development_stub"
    settings.AI_LOCAL_EMBEDDING_URL = ""
    settings.AI_LOCAL_EMBEDDING_MODEL = ""
    settings.AI_LOCAL_VISION_URL = ""
    settings.AI_LOCAL_VISION_MODEL = ""


@pytest.mark.django_db(transaction=True)
def test_conversation_is_authenticated_managed_and_does_not_persist_chat(assistant_domain):
    from apps.assistant.models import AIJob
    anonymous = APIClient().post('/api/v1/assistant/conversation/', {'messages': [{'role': 'user', 'content': '黑色耳机'}]}, format='json')
    assert anonymous.status_code in (401, 403)
    original_count = Item.objects.count()
    with patch('apps.assistant.views.converse', return_value={'reply': '最后在哪儿见过？', 'description': '黑色耳机'}):
        result = authenticated_client(assistant_domain).post('/api/v1/assistant/conversation/',
            {'kind': 'LOST', 'messages': [{'role': 'user', 'content': '黑色耳机'}]}, format='json')
    assert result.status_code == 200
    job = AIJob.objects.get(pk=result.data['data']['workflow_id'])
    assert job.status == 'SUCCEEDED'
    assert job.response is None
    assert Item.objects.count() == original_count


def test_provider_output_must_be_grounded_in_the_redacted_source_text():
    provider = Mock()
    provider.extract.return_value = ProviderResult(
        payload={
            "draft": {
                "kind": "LOST",
                "title": "黑色耳机",
                "category_hint": "耳机",
                "brand": "虚构品牌",
                "colors": ["黑色"],
                "occurred_at": None,
                "location_hint": "",
                "public_description": "黑色耳机",
                "uncertain_fields": ["occurred_at", "location_hint"],
                "source_spans": {
                    "title": "黑色耳机",
                    "category_hint": "耳机",
                    "brand": "虚构品牌",
                    "colors": "黑色",
                },
            },
            "follow_up_questions": [],
        },
        provider="test",
        model="test",
        simulated=False,
    )
    with patch("apps.assistant.providers.get_provider", return_value=provider):
        with pytest.raises(ProviderProtocolError):
            extract_structured_description("丢了一副黑色耳机", "LOST")


@pytest.fixture
def assistant_domain(db):
    school = School.objects.create(name="寻迹测试大学", code="trace-assistant-school")
    campus = Campus.objects.create(school=school, name="主校区", code="trace-assistant-campus")
    location = CampusLocation.objects.create(campus=campus, name="图书馆", code="trace-assistant-library")
    station = Station.objects.create(
        name="图书馆服务站",
        code="trace-assistant-station",
        location=location,
        address="一楼服务台",
        approval_status=Station.ApprovalStatus.APPROVED,
    )
    category = Category.objects.create(name="耳机", code="trace-assistant-headphones")
    owner = User.objects.create_user(
        "assistant-owner",
        password="SafePassword!2026",
        display_name="测试用户",
    )
    return {
        "school": school,
        "campus": campus,
        "location": location,
        "station": station,
        "category": category,
        "owner": owner,
    }


def authenticated_client(domain):
    client = APIClient()
    client.force_authenticate(domain["owner"])
    client.credentials(HTTP_X_CAMPUS_ID=str(domain["campus"].pk))
    return client


def make_item(domain, **overrides):
    values = {
        "owner": domain["owner"],
        "kind": Item.Kind.FOUND,
        "category": domain["category"],
        "title": "图书馆拾到黑色 Sony 耳机",
        "description": "黑色入耳式耳机，带充电盒。",
        "brand": "Sony",
        "color": "黑色",
        "occurred_at": timezone.now() - timedelta(hours=1),
        "location": domain["location"],
        "station": domain["station"],
        "review_status": Item.ReviewStatus.APPROVED,
        "business_status": Item.BusinessStatus.OPEN,
    }
    values.update(overrides)
    return Item.objects.create(**values)


def structured_draft():
    return {
        "kind": "LOST",
        "title": "寻找黑色 Sony 耳机",
        "category_hint": "耳机",
        "brand": "Sony",
        "colors": ["黑色"],
        "occurred_at": None,
        "location_hint": "图书馆",
        "public_description": "黑色 Sony 耳机，可能落在图书馆。",
        "uncertain_fields": ["occurred_at"],
        "source_spans": {
            "title": "黑色 Sony 耳机",
            "category_hint": "耳机",
            "brand": "Sony",
            "colors": "黑色",
            "location_hint": "图书馆",
        },
    }


@pytest.mark.django_db(transaction=True)
def test_agent_publishes_once_only_after_explicit_confirmation(assistant_domain):
    import uuid
    client = authenticated_client(assistant_domain)
    payload = {'kind':'LOST','title':'遗失黑色耳机','description':'黑色耳机，盒盖有划痕。',
        'category':assistant_domain['category'].pk,'location':assistant_domain['location'].pk,
        'occurred_at':timezone.now().isoformat(),'brand':'','color':'黑色'}
    key=str(uuid.uuid4())
    url='/api/v1/assistant/agent/actions/'
    assert client.post(url,{'action':'publish','payload':payload,'key':key},format='json').status_code==400
    assert Item.objects.count()==0
    body={'action':'publish','payload':payload,'confirmed':True,'key':key}
    first=client.post(url,body,format='json'); second=client.post(url,body,format='json')
    assert first.status_code==second.status_code==200
    assert first.data['data']['item']['id']==second.data['data']['item']['id']
    assert Item.objects.count()==1
    body['payload']={**payload,'title':'修改后的标题'}
    assert client.post(url,body,format='json').status_code==400


@pytest.mark.django_db(transaction=True)
def test_agent_claim_and_direct_handover_respect_both_participants(assistant_domain):
    import uuid
    from apps.claims.models import Claim
    from apps.claims.services import decide_claim, confirm_direct_handover
    finder=User.objects.create_user('agent-finder',password='SafePassword!2026')
    found=make_item(assistant_domain,owner=finder,station=None)
    lost=make_item(assistant_domain,kind='LOST',station=None)
    client=authenticated_client(assistant_domain);url='/api/v1/assistant/agent/actions/'
    def invoke(action,payload):
        return client.post(url,{'action':action,'payload':payload,'confirmed':True,'key':str(uuid.uuid4())},format='json')
    create=invoke('claim',{'found_item_id':str(found.pk),'related_lost_item_id':str(lost.pk),'statement':'充电盒内侧有我刻的小星星'})
    assert create.status_code==200
    claim_id=create.data['data']['claim']['id']
    assert invoke('start_handover',{'claim_id':claim_id}).status_code==400
    claim=Claim.objects.get(pk=claim_id)
    decide_claim(claim,finder,'APPROVE','已核对隐蔽特征')
    assert invoke('start_handover',{'claim_id':claim_id}).status_code==200
    own_confirmation=invoke('confirm_handover',{'claim_id':claim_id})
    assert own_confirmation.data['data']['claim']['status']=='HANDOVER_PENDING'
    claim.refresh_from_db();confirm_direct_handover(claim,finder)
    refreshed=invoke('status',{'claim_id':claim_id})
    assert refreshed.data['data']['claim']['status']=='COMPLETED'
    from apps.assistant.models import AgentActionReceipt
    original_key=AgentActionReceipt.objects.filter(owner=assistant_domain['owner']).earliest('created_at').key
    replay=client.post(url,{'action':'claim','payload':{'found_item_id':str(found.pk),'related_lost_item_id':str(lost.pk),'statement':'充电盒内侧有我刻的小星星'},'confirmed':True,'key':str(original_key)},format='json')
    assert replay.data['data']['claim']['status']=='COMPLETED'
    claim.refresh_from_db();claim.claimant_deleted_at=timezone.now();claim.save(update_fields=['claimant_deleted_at'])
    assert invoke('status',{'claim_id':claim_id}).status_code==404
    outsider=User.objects.create_user('agent-outsider',password='SafePassword!2026')
    client.force_authenticate(outsider)
    assert invoke('status',{'claim_id':claim_id}).status_code==404


@pytest.mark.django_db(transaction=True)
def test_agent_publication_cannot_cross_campus(assistant_domain):
    import uuid
    other=Campus.objects.create(school=assistant_domain['school'],name='其他校区',code='agent-other-campus')
    location=CampusLocation.objects.create(campus=other,name='其他校区图书馆',code='agent-other-library')
    response=authenticated_client(assistant_domain).post('/api/v1/assistant/agent/actions/',{
        'action':'publish','confirmed':True,'key':str(uuid.uuid4()),'payload':{'kind':'LOST','title':'遗失耳机','description':'黑色耳机遗失了',
        'category':assistant_domain['category'].pk,'location':location.pk,'occurred_at':timezone.now().isoformat()}},format='json')
    assert response.status_code==400
    assert Item.objects.count()==0


@pytest.mark.django_db(transaction=True)
def test_agent_station_appointment_verification_and_both_confirmations(assistant_domain):
    import uuid
    from apps.claims.services import submit_claim, decide_claim, confirm_handover
    finder=User.objects.create_user('agent-station-finder',password='SafePassword!2026')
    coordinator=User.objects.create_user('agent-station-admin',password='SafePassword!2026',role='ADMIN')
    found=make_item(assistant_domain,owner=finder,station=None)
    lost=make_item(assistant_domain,kind='LOST',station=None)
    claim=submit_claim(found,assistant_domain['owner'],'盒盖内侧有独特星星',{},lost)
    decide_claim(claim,finder,'APPROVE','已核对')
    client=authenticated_client(assistant_domain)
    def invoke(action,payload):
        return client.post('/api/v1/assistant/agent/actions/',{'action':action,'payload':payload,'confirmed':True,'key':str(uuid.uuid4())},format='json')
    scheduled=invoke('schedule',{'claim_id':str(claim.pk),'station_id':assistant_domain['station'].pk,'scheduled_at':(timezone.now()+timedelta(days=1)).isoformat()})
    assert scheduled.status_code==200
    code=scheduled.data['data']['one_time_code']
    assert len(code)==6
    assert invoke('confirm_station_handover',{'claim_id':str(claim.pk)}).status_code==400
    verify_url=f'/api/v1/claims/{claim.pk}/handover/verify/'
    wrong='111111' if code=='000000' else '000000'
    assert client.post(verify_url,{'code':wrong},format='json').status_code==400
    claim.refresh_from_db();assert claim.appointment.failed_attempts==1
    assert client.post(verify_url,{'code':code},format='json').status_code==200
    own=invoke('confirm_station_handover',{'claim_id':str(claim.pk)})
    assert own.status_code==200
    assert own.data['data']['claim']['status']=='HANDOVER_PENDING'
    claim.refresh_from_db();confirm_handover(claim,coordinator)
    assert invoke('status',{'claim_id':str(claim.pk)}).data['data']['claim']['status']=='COMPLETED'


@pytest.mark.django_db(transaction=True)
def test_agent_can_supplement_only_own_claim_when_requested(assistant_domain):
    import uuid
    from apps.claims.services import submit_claim, decide_claim
    finder=User.objects.create_user('agent-proof-finder',password='SafePassword!2026')
    found=make_item(assistant_domain,owner=finder,station=None)
    lost=make_item(assistant_domain,kind='LOST',station=None)
    claim=submit_claim(found,assistant_domain['owner'],'盒内有星星',{},lost)
    decide_claim(claim,finder,'NEEDS_INFO','请补充刻字细节')
    body={'action':'supplement','payload':{'claim_id':str(claim.pk),'statement':'内侧刻有蓝色六角星和日期'},'confirmed':True,'key':str(uuid.uuid4())}
    result=authenticated_client(assistant_domain).post('/api/v1/assistant/agent/actions/',body,format='json')
    assert result.status_code==200
    assert result.data['data']['claim']['status']=='SUBMITTED'
    assert 'evidence' not in result.data['data']['claim']
    claim.refresh_from_db();assert '六角星' in claim.statement


@pytest.mark.django_db(transaction=True)
def test_agent_chat_searches_without_another_form_confirmation(assistant_domain):
    make_item(assistant_domain)
    with patch('apps.assistant.views.converse',return_value={'reply':'不要重复确认','description':'黑色Sony耳机，图书馆遗失','provider':{'simulated':False}}):
        result=authenticated_client(assistant_domain).post('/api/v1/assistant/conversation/',
            {'messages':[{'role':'user','content':'黑色Sony耳机，图书馆遗失'}]},format='json')
    assert result.status_code==200
    assert result.data['data']['stage']=='results'
    assert result.data['data']['candidates']
    assert result.data['data']['tool_trace'][-1]['status']=='completed'


@pytest.mark.django_db(transaction=True)
def test_confirmed_photo_goes_directly_to_extraction_and_search(assistant_domain):
    make_item(assistant_domain)
    source='图片外观（我已核对）：黑色耳机，盒盖有一道浅划痕。'
    with patch('apps.assistant.views.converse') as chat:
        result=authenticated_client(assistant_domain).post('/api/v1/assistant/conversation/',{'messages':[{'role':'user','content':source}]},format='json')
    assert result.status_code==200
    assert result.data['data']['stage']=='results'
    assert '盒盖有一道浅划痕' in result.data['data']['description']
    assert '图片外观' not in result.data['data']['description']
    chat.assert_not_called()


def test_server_owned_title_does_not_depend_on_model_generated_text():
    draft = structured_draft()
    source = draft["public_description"]
    draft["title"] = ""
    draft["public_description"] = ""
    provider = Mock()
    provider.extract.return_value = ProviderResult(
        payload={"draft": draft, "follow_up_questions": []},
        provider="test", model="test", simulated=False,
    )
    with patch("apps.assistant.providers.get_provider", return_value=provider):
        result = extract_structured_description(source, "LOST")
    assert result.payload["draft"]["title"] == "寻找黑色 Sony 耳机"
    assert result.payload["draft"]["public_description"] != source
    assert "可能地点：图书馆" in result.payload["draft"]["public_description"]


@pytest.mark.django_db
def test_confirmed_color_and_category_outweigh_higher_semantic_similarity(assistant_domain, settings):
    settings.AI_LOCAL_EMBEDDING_URL = "http://127.0.0.1:8082/v1"
    settings.AI_LOCAL_EMBEDDING_MODEL = "test-six-factor"
    from django.core.cache import cache
    cache.clear()
    black = make_item(assistant_domain, title="黑色耳机")
    blue = make_item(assistant_domain, title="蓝色耳机", color="蓝色")
    phone_category = Category.objects.create(name="手机", code="rank-phone")
    phone = make_item(assistant_domain, title="黑色手机", category=phone_category)
    vectors = {"黑色耳机": [.8, .6], "蓝色耳机": [.95, .3122499], "黑色手机": [1, 0]}
    def embed(texts):
        return [next((v for title, v in vectors.items() if title in text), [1, 0]) for text in texts]
    draft = structured_draft()
    draft.update(title="找耳机", public_description="寻找听音乐的设备", brand="", location_hint="")
    with patch("apps.assistant.local_models.embeddings", side_effect=embed):
        response = authenticated_client(assistant_domain).post("/api/v1/assistant/search/",
            {"draft": draft, "limit": 3}, format="json")
    assert response.status_code == 200
    rows = response.data['data']['candidates']
    assert [row['id'] for row in rows] == [str(black.pk)]
    assert rows[0]['ranking']['acceptance_policy']['version'] == 'evidence_gate_v1'
    # Preserve the raw-ranking contract while the API suppresses weak matches.
    from apps.assistant.ranking import rerank
    raw = rerank(draft, [(.8, black), (.95, blue), (1, phone)])
    assert [row[2].pk for row in raw] == [black.pk, blue.pk, phone.pk]
    assert raw[1][3]['conflicts'] == ['颜色已知不同']
    assert '类别已知不同' in raw[2][3]['conflicts']
    assert rows[0]['ranking']['factors']['brand'] is None
    draft['colors'] = ['绿色']
    with patch('apps.assistant.local_models.embeddings', side_effect=embed):
        empty = authenticated_client(assistant_domain).post('/api/v1/assistant/search/',
            {'draft': draft, 'limit': 3}, format='json')
    assert empty.status_code == 200
    assert empty.data['data']['candidates'] == []
    assert empty.data['data']['citations'] == []
    assert empty.data['data']['retrieval_method'] == 'semantic_six_factor_v2'


@pytest.mark.django_db
def test_semantic_retrieval_ranks_vectors_and_excludes_unpublished(assistant_domain, settings):
    settings.AI_LOCAL_EMBEDDING_URL = "http://127.0.0.1:8082/v1"
    settings.AI_LOCAL_EMBEDDING_MODEL = "test-semantic-permissions"
    from django.core.cache import cache
    cache.clear()
    visible = make_item(assistant_domain)
    hidden = make_item(assistant_domain, title="隐藏线索", review_status=Item.ReviewStatus.PENDING)
    other_campus = Campus.objects.create(school=assistant_domain["school"], name="另一校区", code="semantic-other")
    other_location = CampusLocation.objects.create(campus=other_campus, name="另一图书馆", code="semantic-other-lib")
    make_item(assistant_domain, location=other_location)
    sent = []
    def embed(texts):
        sent.extend(texts)
        return [[1.0, 0.0] for _ in texts]
    with patch("apps.assistant.local_models.embeddings", side_effect=embed):
        response = authenticated_client(assistant_domain).post("/api/v1/assistant/search/",
            {"draft": structured_draft(), "limit": 5}, format="json")
    assert response.status_code == 200
    data = response.data["data"]
    assert data["semantic_retrieval"] is True
    assert [row["id"] for row in data["candidates"]] == [str(visible.pk)]
    assert len(sent) == 2  # one authorized public record plus the query
    assert all(hidden.title not in text for text in sent)


@pytest.mark.django_db
def test_capabilities_expose_only_the_restricted_read_only_tools():
    response = APIClient().get("/api/v1/assistant/capabilities/")
    assert response.status_code == 200
    assert response.data["data"]["provider"] == {
        "mode": "development_stub",
        "simulated": True,
        "configured": True,
    }
    tools = response.data["data"]["tools"]
    assert {entry["name"] for entry in tools} == {
        "query_public_items",
        "read_public_item",
        "query_service_stations",
        "generate_pending_draft",
    }
    assert all(entry["read_only"] for entry in tools)
    assert not any(
        forbidden in entry["name"]
        for entry in tools
        for forbidden in ("approve", "delete", "handover")
    )


@pytest.mark.django_db
def test_prepare_is_explicitly_simulated_validated_and_does_not_persist(assistant_domain):
    before = Item.objects.count()
    response = authenticated_client(assistant_domain).post(
        "/api/v1/assistant/prepare/",
        {
            "kind": "LOST",
            "description": "我在图书馆丢了一副黑色 Sony 耳机，电话 13812345678。",
        },
        format="json",
    )
    assert response.status_code == 200
    data = response.data["data"]
    assert data["provider"] == {
        "name": "development_stub",
        "model": "local_rules_v1",
        "simulated": True,
    }
    assert data["draft"]["category_hint"] == "耳机"
    assert data["draft"]["brand"] == "Sony"
    assert "13812345678" not in data["draft"]["public_description"]
    assert "[手机号已隐藏]" not in data["draft"]["public_description"]
    assert data["stages"][1]["status"] == "waiting"
    assert Item.objects.count() == before

    invalid = authenticated_client(assistant_domain).post(
        "/api/v1/assistant/prepare/",
        {"kind": "LOST", "description": "丢了一串钥匙", "unexpected": True},
        format="json",
    )
    assert invalid.status_code == 400


@pytest.mark.django_db
def test_search_cites_only_real_public_same_campus_candidates(assistant_domain):
    public = make_item(assistant_domain)
    make_item(
        assistant_domain,
        title="未公开黑色 Sony 耳机",
        review_status=Item.ReviewStatus.DRAFT,
    )
    other_school = School.objects.create(name="另一所大学", code="trace-other-school")
    other_campus = Campus.objects.create(school=other_school, name="其他校区", code="trace-other-campus")
    other_location = CampusLocation.objects.create(campus=other_campus, name="其他图书馆", code="trace-other-library")
    make_item(assistant_domain, title="跨校区黑色 Sony 耳机", location=other_location, station=None)

    response = authenticated_client(assistant_domain).post(
        "/api/v1/assistant/search/",
        {"draft": structured_draft(), "limit": 5},
        format="json",
    )
    assert response.status_code == 200
    data = response.data["data"]
    assert data["semantic_retrieval"] is False
    assert [entry["id"] for entry in data["candidates"]] == [str(public.pk)]
    assert data["citations"] == [
        {"id": f"item:{public.pk}", "item_id": str(public.pk), "url": f"/items/{public.pk}"}
    ]
    assert "location_detail" not in data["candidates"][0]
    assert data["stations"][0]["name"] == "图书馆服务站"


@pytest.mark.django_db
def test_draft_preview_validates_without_creating_or_submitting_an_item(assistant_domain):
    before = Item.objects.count()
    response = authenticated_client(assistant_domain).post(
        "/api/v1/assistant/draft-preview/",
        {
            "kind": "LOST",
            "title": "寻找黑色耳机",
            "description": "黑色 Sony 耳机，可能落在图书馆。",
            "category": assistant_domain["category"].pk,
            "occurred_at": timezone.now().isoformat(),
            "location": assistant_domain["location"].pk,
            "brand": "Sony",
            "color": "黑色",
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.data["data"]["persisted"] is False
    assert response.data["data"]["requires_user_confirmation"] is True
    assert response.data["data"]["payload"]["location_name"] == "图书馆"
    assert Item.objects.count() == before

