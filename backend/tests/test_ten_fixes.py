"""Regression coverage for the ten findings in report 48."""
from unittest.mock import patch
from pathlib import Path
import json
import pytest
from django.db import connection, DatabaseError
from rest_framework.request import Request
from apps.accounts.models import User
from apps.items.models import Favorite, Item, MediaAsset
from apps.messaging.models import Conversation, ConversationParticipant, Message
from apps.stations.models import Campus
from apps.assistant.publication import date_evidence
from tests.test_assistant_workflow import assistant_domain, authenticated_client, make_item, structured_draft, isolate_inference_configuration
from tests.test_agent_photos_review import photo
from apps.items.models import Subscription
from apps.notifications.models import Notification
from apps.notifications.services import notify_public_item

pytestmark = [pytest.mark.mysql, pytest.mark.django_db(transaction=True)]

def test_fixed_favorite_exposes_new_private_title(assistant_domain):
    other = User.objects.create_user('audit-other')
    item = make_item(assistant_domain)
    favorite = Favorite.objects.create(user=other, item=item)
    Item.objects.filter(pk=item.pk).update(review_status='DRAFT', title='仅草稿的新私有标题')
    client = authenticated_client(assistant_domain)
    client.force_authenticate(other)
    result = client.get('/api/v1/items/favorites/')
    rows = result.data['data']['items']
    assert rows == []
    assert client.get(f'/api/v1/items/{item.pk}/').status_code == 404
    assert client.delete(f'/api/v1/items/favorites/{favorite.pk}/').status_code == 204


def test_fixed_messages_do_not_follow_selected_campus(assistant_domain):
    item = make_item(assistant_domain)
    chat = Conversation.objects.create(subject='校区A对话', item=item)
    ConversationParticipant.objects.create(conversation=chat, user=assistant_domain['owner'])
    other = Campus.objects.create(school=assistant_domain['school'], code='audit-other-campus', name='校区B')
    client = authenticated_client(assistant_domain)
    client.credentials(HTTP_X_CAMPUS_ID=str(other.pk))
    result = client.get('/api/v1/messages/')
    assert result.status_code == 200, result.data
    assert result.data['data']['total'] == 0
    assert client.get(f'/api/v1/messages/{chat.pk}/').status_code == 404
    assert client.post(f'/api/v1/messages/{chat.pk}/messages/', {'body':'你好'}, format='json').status_code == 404


def test_fixed_long_message_exceeds_declared_limit(assistant_domain):
    chat = Conversation.objects.create(subject='消息长度', campus=assistant_domain['campus'])
    ConversationParticipant.objects.create(conversation=chat, user=assistant_domain['owner'])
    client = authenticated_client(assistant_domain)
    result = client.post(f'/api/v1/messages/{chat.pk}/messages/', {'body':'测'*5000}, format='json')
    assert result.status_code == 400, result.data
    assert not Message.objects.filter(conversation=chat).exists()


def test_fixed_map_includes_closed_items(assistant_domain):
    make_item(assistant_domain, business_status='CLOSED')
    client = authenticated_client(assistant_domain)
    summary = client.get('/api/v1/items/map-summary/').data['data']
    listing = client.get('/api/v1/items/').data['data']
    assert listing['total'] == 0
    assert sum(row['count'] for row in summary['locations']) == 0 and summary['total'] == 0


def test_fixed_forgetting_clock_clears_known_day(assistant_domain):
    from apps.assistant.agent_tools import run_search
    from apps.assistant.contracts import StructuredItemDraftSerializer
    parsed = StructuredItemDraftSerializer(data=structured_draft())
    parsed.is_valid(raise_exception=True)
    draft = dict(parsed.validated_data)
    client = authenticated_client(assistant_domain)
    request = Request(client.get('/api/v1/assistant/capabilities/').wsgi_request)
    request.user = assistant_domain['owner']
    source = '昨天丢了一副黑色Sony耳机，可能在图书馆'
    result = {'description':source,'_latest_user':'具体时间我记不清了','_safe_draft':draft,'intent':'ask'}
    response = run_search(request,result,'LOST',[],{'event_day':'2026-11-16','reference_day':'2026-11-17','draft':draft,'source':source})
    assert response['publication']['occurred_date'] == '2026-11-16'


def test_fixed_alternative_date_still_becomes_certain():
    result = date_evidence('昨天或前天', reference_day='2026-11-17')
    assert result == ''


def test_fixed_form_upload_commit_failure_leaves_files(assistant_domain, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    item = make_item(assistant_domain, review_status='DRAFT')
    client = authenticated_client(assistant_domain)
    with patch.object(connection, 'commit', side_effect=DatabaseError('audit commit failure')):
        with pytest.raises(DatabaseError):
            client.post(f'/api/v1/items/{item.pk}/media/', {'files':[photo()]}, format='multipart')
    files = [path for path in tmp_path.rglob('*') if path.is_file()]
    assert MediaAsset.objects.count() == 0
    assert len(files) == 0


def test_subscriptions_publish_threshold_preference_scope_and_dedup(assistant_domain):
    from apps.items.services import submit_item
    from django.db import transaction
    user = User.objects.create_user('subscription-reader')
    other = Campus.objects.create(school=assistant_domain['school'], name='其他', code='subscription-other')
    included = Subscription.objects.create(user=user,campus=assistant_domain['campus'],name='黑色耳机',criteria={'q':'黑色耳机','kind':'FOUND'},minimum_score=.9)
    Subscription.objects.create(user=user,campus=other,name='其他校区',criteria={'q':'耳机'},minimum_score=0)
    Subscription.objects.create(user=user,campus=assistant_domain['campus'],name='暂停',criteria={'q':'耳机'},is_active=False)
    Subscription.objects.create(user=user,campus=assistant_domain['campus'],name='过高',criteria={'q':'黑色耳机橙色'},minimum_score=1)
    item = make_item(assistant_domain, review_status='DRAFT')
    submit_item(item,assistant_domain['owner'])
    row = Notification.objects.get(user=user)
    assert row.category == 'MATCH' and row.campus_id == assistant_domain['campus'].pk
    assert row.metadata['subscription_id'] == included.pk and row.metadata['score'] == 1
    item.refresh_from_db()
    notify_public_item(item)
    assert Notification.objects.filter(user=user).count() == 1
    user.notification_preferences={'match':False}
    user.save(update_fields=['notification_preferences'])
    notify_public_item(make_item(assistant_domain))
    assert Notification.objects.filter(user=user).count() == 1
    user.notification_preferences={}
    user.save(update_fields=['notification_preferences'])
    try:
        with transaction.atomic():
            submit_item(make_item(assistant_domain,review_status='DRAFT'),assistant_domain['owner'])
            raise RuntimeError('rollback')
    except RuntimeError:
        pass
    assert Notification.objects.filter(user=user).count() == 1


def test_claim_and_message_events_notify_without_private_preview(assistant_domain):
    from apps.claims.services import submit_claim, decide_claim
    finder = User.objects.create_user('event-finder')
    found = make_item(assistant_domain,owner=finder)
    lost = make_item(assistant_domain,kind='LOST')
    claim = submit_claim(found,assistant_domain['owner'],statement='秘密核验标记A12345',evidence={'proof':'秘密证据'},related_lost_item=lost)
    assert Notification.objects.filter(user=finder,category='CLAIM').count() == 1
    decide_claim(claim,finder,'APPROVE','核验通过')
    claimant = assistant_domain['owner']
    assert Notification.objects.filter(user=claimant,category='CLAIM').count() == 1
    chat = Conversation.objects.get(claim=claim)
    assert chat.campus_id == assistant_domain['campus'].pk
    client = authenticated_client(assistant_domain)
    before = Notification.objects.filter(user=finder).count()
    assert client.post(f'/api/v1/messages/{chat.pk}/messages/', {'body':'私密沟通内容'},format='json').status_code == 201
    assert Notification.objects.filter(user=finder).count() == before+1
    for row in Notification.objects.all():
        assert '秘密' not in row.body and '私密沟通内容' not in row.body
    finder.notification_preferences={'claim':False}
    finder.save(update_fields=['notification_preferences'])
    client.post(f'/api/v1/messages/{chat.pk}/messages/', {'body':'第二条'},format='json')
    assert Notification.objects.filter(user=finder).count() == before+1


def test_invalid_message_types_and_limit(assistant_domain):
    chat = Conversation.objects.create(subject='长度',campus=assistant_domain['campus'])
    ConversationParticipant.objects.create(conversation=chat,user=assistant_domain['owner'])
    client = authenticated_client(assistant_domain)
    for value in ['', ' '*3, 123, {}, [], 'a'*4001]:
        assert client.post(f'/api/v1/messages/{chat.pk}/messages/',{'body':value},format='json').status_code == 400
    assert client.post(f'/api/v1/messages/{chat.pk}/messages/',{'body':'a'*4000},format='json').status_code == 201


def test_config_states_support_copy_edit_publish_history(assistant_domain):
    from apps.matching.engine import DEFAULT_WEIGHTS
    user=assistant_domain['owner'];user.role='ADMIN';user.save(update_fields=['role'])
    client=authenticated_client(assistant_domain)
    base='/api/v1/admin/matching-configs/'
    def create(version):
        response=client.post(base,{'name':'参数测试','version':version,'weights':DEFAULT_WEIGHTS},format='json')
        assert response.status_code==201,response.data
        return response.data
    first=create('ten-first')
    assert first['editable'] and first['state']=='DRAFT'
    assert client.patch(f'{base}{first["id"]}/',{'name':'新名称'},format='json').status_code==200
    assert client.post(f'{base}{first["id"]}/publish/').data['data']['state']=='ACTIVE'
    second=create('ten-copy')
    client.post(f'{base}{second["id"]}/publish/')
    old=client.get(f'{base}{first["id"]}/').data
    assert not old['editable'] and old['state']=='HISTORICAL'
    assert client.patch(f'{base}{first["id"]}/',{'name':'不能改'},format='json').status_code==400
