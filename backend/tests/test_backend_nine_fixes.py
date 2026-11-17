import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from django.db import DatabaseError, IntegrityError, close_old_connections, connection, transaction
from django.utils import timezone
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.administration.serializers import AlgorithmConfigSerializer
from apps.assistant.models import AgentActionReceipt
from apps.assistant.publication import date_evidence
from apps.items.media import upload_item_media
from apps.items.models import Item, MediaAsset, Subscription
from apps.matching.engine import DEFAULT_WEIGHTS
from apps.matching.models import AlgorithmConfig, AlgorithmPublicationLock, IndexVersion
from apps.stations.models import Campus
from tests.test_assistant_workflow import assistant_domain, authenticated_client, isolate_inference_configuration, make_item, structured_draft
from tests.test_agent_photos_review import photo, publication

pytestmark = [pytest.mark.mysql, pytest.mark.django_db(transaction=True)]


def admin_client(domain):
    domain['owner'].role = 'ADMIN'
    domain['owner'].save(update_fields=['role'])
    return authenticated_client(domain)


def config(domain, version):
    return AlgorithmConfig.objects.create(name='版本', version=version, weights=DEFAULT_WEIGHTS, created_by=domain['owner'])


def test_published_and_retired_configs_are_immutable(assistant_domain):
    client = admin_client(assistant_domain)
    first, second = config(assistant_domain, 'immutable1'), config(assistant_domain, 'immutable2')
    base = '/api/v1/admin/matching-configs/'
    assert client.patch(f'{base}{first.pk}/', {'name': '可编辑草稿'}, format='json').status_code == 200
    for row in (first, second):
        assert client.post(f'{base}{row.pk}/publish/').status_code == 200
    assert client.patch(f'{base}{first.pk}/', {'weights': DEFAULT_WEIGHTS}, format='json').status_code == 400
    assert client.patch(f'{base}{second.pk}/', {'version': 'changed'}, format='json').status_code == 400
    first.refresh_from_db()
    assert first.version == 'immutable1' and first.published_at and not first.is_published
    from django.core.exceptions import ValidationError
    first.weights = {**DEFAULT_WEIGHTS, 'text': 0.7}
    with pytest.raises(ValidationError):
        first.save()


def test_concurrent_publication_and_database_constraint(assistant_domain):
    admin_client(assistant_domain)
    rows = [config(assistant_domain, f'parallel{i}') for i in range(2)]
    AlgorithmPublicationLock.objects.get_or_create(pk=1)
    barrier = Barrier(2)
    def publish(pk):
        close_old_connections()
        try:
            client = authenticated_client(assistant_domain)
            barrier.wait(timeout=10)
            return client.post(f'/api/v1/admin/matching-configs/{pk}/publish/').status_code
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(publish, [row.pk for row in rows])) == [200, 200]
    assert AlgorithmConfig.objects.filter(is_published=True).count() == 1
    inactive = AlgorithmConfig.objects.get(is_published=False)
    with pytest.raises(IntegrityError), transaction.atomic():
        AlgorithmConfig.objects.filter(pk=inactive.pk).update(is_published=True, active_slot=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        AlgorithmConfig.objects.filter(pk=inactive.pk).update(is_published=True)


def test_index_referenced_config_is_immutable_even_before_publication(assistant_domain):
    client = admin_client(assistant_domain)
    row = config(assistant_domain, 'indexed-draft')
    IndexVersion.objects.create(version='index1', document_count=1, vocabulary_size=1, artifact_path='test', corpus_checksum='a'*64, config=row)
    assert client.patch(f'/api/v1/admin/matching-configs/{row.pk}/', {'name':'changed'}, format='json').status_code == 400


@pytest.mark.parametrize('field,value', [
    ('weights', []), ('weights', {**DEFAULT_WEIGHTS, 'text': 'bad'}),
    ('weights', {**DEFAULT_WEIGHTS, 'text': float('nan')}),
    ('weights', {**DEFAULT_WEIGHTS, 'text': True}),
    ('weights', {**DEFAULT_WEIGHTS, 'text': 10**1000}),
    ('thresholds', {'min_score': 2}), ('thresholds', {'time_tau_days': 0}),
    ('thresholds', {'min_score': float('inf')}), ('thresholds', {'unknown': 1}),
    ('preprocessing', {'aliases': []}), ('preprocessing', {'stop_words': 'word'}),
    ('preprocessing', {'custom_words': [False]}), ('preprocessing', {'unknown': 1}),
])
def test_configuration_invalid_inputs_are_field_errors(field, value):
    serializer = AlgorithmConfigSerializer(data={field: value}, partial=True)
    assert not serializer.is_valid() and field in serializer.errors


def test_media_authorization_applies_to_original_and_thumbnail(assistant_domain, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    item = make_item(assistant_domain, review_status='DRAFT')
    asset = upload_item_media(item.pk, assistant_domain['owner'], [photo()])[0]
    anonymous = APIClient()
    owner = authenticated_client(assistant_domain)
    for field in (asset.file, asset.thumbnail):
        url = field.url + f'?campus={assistant_domain["campus"].pk}'
        assert anonymous.get(url).status_code == 404
        response = owner.get(url)
        assert response.status_code == 200 and response['Cache-Control'] == 'private, no-store'
        response.close()
        Item.objects.filter(pk=item.pk).update(review_status='APPROVED', business_status='OPEN')
        response = anonymous.get(url)
        assert response.status_code == 200
        response.close()
        Item.objects.filter(pk=item.pk).update(business_status='CLOSED')
        assert anonymous.get(url).status_code == 404
        Item.objects.filter(pk=item.pk).update(review_status='DRAFT', business_status='OPEN')
    assert anonymous.get('/media/../config/settings.py').status_code == 404
    other = Campus.objects.create(school=assistant_domain['school'], name='另一校区', code='media-other')
    owner.credentials(HTTP_X_CAMPUS_ID=str(other.pk))
    assert owner.get(asset.file.url).status_code == 404
    owner.credentials(HTTP_X_CAMPUS_ID=str(assistant_domain['campus'].pk))
    stranger = User.objects.create_user('media-stranger')
    owner.force_authenticate(stranger)
    assert owner.get(asset.file.url).status_code == 404


def test_subscription_is_scoped_to_current_campus(assistant_domain):
    client = authenticated_client(assistant_domain)
    body = {'name': '耳机订阅', 'criteria': {'kind': 'FOUND', 'q': '耳机'}}
    response = client.post('/api/v1/items/subscriptions/', body, format='json')
    assert response.status_code == 201, response.data
    row = Subscription.objects.get(pk=response.data['id'])
    assert row.campus_id == assistant_domain['campus'].pk
    other = Campus.objects.create(school=assistant_domain['school'], name='另校区', code='sub-other')
    client.credentials(HTTP_X_CAMPUS_ID=str(other.pk))
    assert client.get('/api/v1/items/subscriptions/').data['data']['total'] == 0
    assert client.patch(f'/api/v1/items/subscriptions/{row.pk}/', {'name':'跨区'}, format='json').status_code == 404
    assert client.post('/api/v1/items/subscriptions/', {**body, 'criteria': {'location': assistant_domain['location'].pk}}, format='json').status_code == 400


def test_private_media_staff_and_claimant_permissions(assistant_domain, settings, tmp_path):
    from apps.stations.models import StationMembership
    from apps.claims.models import Claim
    settings.MEDIA_ROOT = tmp_path
    item = make_item(assistant_domain)
    asset = upload_item_media(item.pk, assistant_domain['owner'], [photo()])[0]
    item.business_status = 'CLOSED'
    item.save(update_fields=['business_status'])
    client = authenticated_client(assistant_domain)
    url = asset.file.url
    claimant = User.objects.create_user('media-claimant')
    Claim.objects.create(found_item=item, claimant=claimant, statement='测试核验信息')
    client.force_authenticate(claimant)
    response = client.get(url)
    assert response.status_code == 200
    response.close()
    staff = User.objects.create_user('media-staff', role='STAFF')
    client.force_authenticate(staff)
    assert client.get(url).status_code == 404
    StationMembership.objects.create(user=staff, station=assistant_domain['station'], is_active=True)
    response = client.get(url)
    assert response.status_code == 200
    response.close()
    admin = User.objects.create_user('media-admin', role='ADMIN')
    client.force_authenticate(admin)
    response = client.get(url)
    assert response.status_code == 200
    response.close()


@pytest.mark.parametrize('source', ['可能是昨天晚上', '昨天还是前天', '不是昨天', '昨天或者前天', '我不知道是不是昨天'])
def test_uncertain_days_are_not_prefilled(source):
    assert date_evidence(source) == ''


def test_relative_day_anchor_survives_midnight(assistant_domain):
    from apps.assistant.agent_tools import run_search
    from apps.assistant.dialogue_state import read_memory
    from rest_framework.request import Request
    request = Request(authenticated_client(assistant_domain).get('/api/v1/assistant/capabilities/').wsgi_request)
    request.user = assistant_domain['owner']
    draft = structured_draft()
    draft.update(category_hint='耳机', occurred_at=None, appearance_details=[], identity_markers=[])
    result = {'description':'昨天晚上丢失黑色耳机', 'draft': draft, 'intent':'ask'}
    memory = {'reference_day':'2026-11-17', 'event_day':'2026-11-16', 'draft': draft}
    with patch('apps.assistant.agent_tools.extract_structured_description') as extract:
        extract.return_value.payload = {'draft': draft}
        extract.return_value.provider = extract.return_value.model = 'test'
        extract.return_value.simulated = False
        response = run_search(request, result, 'LOST', [], memory)
    state = read_memory(request, response['context_token'])
    assert state['event_day'] == '2026-11-16'
    assert date_evidence('昨天', reference_day='2026-11-17') == '2026-11-16'
    assert date_evidence('可能是昨天。后来确认就是昨天', reference_day='2026-11-17') == '2026-11-16'
    assert date_evidence('不是昨天，是前天', reference_day='2026-11-17') == '2026-11-15'


def test_reconcile_media_preserves_references_and_inflight_files(assistant_domain, settings, tmp_path):
    import os
    from io import StringIO
    from django.core.management import call_command
    settings.MEDIA_ROOT = tmp_path
    item = make_item(assistant_domain, review_status='DRAFT')
    asset = upload_item_media(item.pk, assistant_domain['owner'], [photo()])[0]
    referenced = tmp_path / asset.file.name
    orphan = tmp_path / 'items/old-orphan.webp'
    recent = tmp_path / 'items/inflight.webp'
    orphan.write_bytes(b'orphan')
    recent.write_bytes(b'inflight')
    os.utime(orphan, (1, 1))
    os.utime(referenced, (1, 1))
    output = StringIO()
    call_command('reconcile_media', stdout=output)
    assert orphan.exists() and 'old-orphan.webp' in output.getvalue()
    call_command('reconcile_media', apply=True, stdout=StringIO())
    assert not orphan.exists() and referenced.exists() and recent.exists()


@pytest.mark.parametrize('failure', ['thumbnail', 'asset', 'receipt', 'commit'])
def test_failed_photo_publication_leaves_no_files_or_records(assistant_domain, settings, tmp_path, failure):
    settings.MEDIA_ROOT = tmp_path
    client = authenticated_client(assistant_domain)
    before = Item.objects.count()
    body = dict(action='publish', payload=json.dumps(publication(assistant_domain)), confirmed='true', key=str(uuid.uuid4()), photos=[photo()])
    if failure == 'asset':
        target = patch.object(MediaAsset, 'save', side_effect=RuntimeError('asset failure'))
    elif failure == 'receipt':
        original = AgentActionReceipt.save
        def save(receipt, *args, **kwargs):
            if kwargs.get('update_fields') == ['result']:
                raise RuntimeError('receipt failure')
            return original(receipt, *args, **kwargs)
        target = patch.object(AgentActionReceipt, 'save', save)
    elif failure == 'commit':
        target = patch.object(connection, 'commit', side_effect=DatabaseError('commit failure'))
    else:
        from apps.items.storage_journal import save_file
        def save(field, name, content):
            save_file(field, name, content)
            if field.field.name == 'thumbnail':
                raise RuntimeError('thumbnail failed after write')
        target = patch('apps.items.media.save_file', save)
    with target, pytest.raises((RuntimeError, DatabaseError)):
        client.post('/api/v1/assistant/agent/actions/', body, format='multipart')
    assert Item.objects.count() == before
    assert not MediaAsset.objects.exists() and not AgentActionReceipt.objects.exists()
    assert not [path for path in tmp_path.rglob('*') if path.is_file()]
