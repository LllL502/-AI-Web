import json
import uuid
from io import BytesIO

import pytest
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.accounts.models import User
from apps.claims.models import Claim
from apps.items.models import Item
from tests.test_assistant_workflow import assistant_domain, authenticated_client, isolate_inference_configuration, make_item

pytestmark = [pytest.mark.mysql, pytest.mark.django_db(transaction=True)]


def publication(domain):
    return dict(kind='FOUND', title='拾到蓝色耳机', description='蓝色耳机，盒盖有划痕。',
                category=domain['category'].pk, location=domain['location'].pk,
                occurred_at=timezone.now().isoformat())


def photo():
    data = BytesIO()
    Image.new('RGB', (80, 60), 'blue').save(data, format='PNG')
    return SimpleUploadedFile('earphones.png', data.getvalue(), content_type='image/png')


def test_agent_photo_publication_is_atomic_and_idempotent(assistant_domain, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client = authenticated_client(assistant_domain)
    key = str(uuid.uuid4())
    body = dict(action='publish', payload=json.dumps(publication(assistant_domain)), confirmed='true', key=key)
    first = client.post('/api/v1/assistant/agent/actions/', {**body, 'photos': [photo()]}, format='multipart')
    assert first.status_code == 200, first.data
    item = Item.objects.get(pk=first.data['data']['item']['id'])
    assert item.kind == 'FOUND' and not item.is_demo
    asset = item.media.get()
    assert asset.width == 80 and asset.file.storage.exists(asset.file.name)
    second = client.post('/api/v1/assistant/agent/actions/', {**body, 'photos': [photo()]}, format='multipart')
    assert second.status_code == 200
    assert second.data['data']['item']['id'] == str(item.pk)
    assert item.media.count() == 1


def test_invalid_photo_does_not_leave_a_publication(assistant_domain, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client = authenticated_client(assistant_domain)
    before = Item.objects.count()
    response = client.post('/api/v1/assistant/agent/actions/', dict(action='publish',
        payload=json.dumps(publication(assistant_domain)), confirmed='true', key=str(uuid.uuid4()),
        photos=[SimpleUploadedFile('fake.png', b'not-an-image', content_type='image/png')]), format='multipart')
    assert response.status_code == 400
    assert Item.objects.count() == before


def test_photo_publication_requires_confirmation(assistant_domain):
    client = authenticated_client(assistant_domain)
    before = Item.objects.count()
    response = client.post('/api/v1/assistant/agent/actions/', dict(action='publish',
        payload=json.dumps(publication(assistant_domain)), confirmed='false', key=str(uuid.uuid4()),
        photos=[photo()]), format='multipart')
    assert response.status_code == 400
    assert Item.objects.count() == before


def test_finder_can_review_but_claimant_and_unrelated_user_cannot(assistant_domain):
    finder = assistant_domain['owner']
    claimant = User.objects.create_user('photo-review-claimant', password='TestOnly!2026')
    unrelated = User.objects.create_user('photo-review-unrelated', password='TestOnly!2026')
    found = make_item(assistant_domain)
    lost = Item.objects.create(owner=claimant, kind='LOST', category=found.category, location=found.location,
        title='寻找耳机', description='蓝色耳机', occurred_at=timezone.now(), review_status='APPROVED')
    claim = Claim.objects.create(found_item=found, related_lost_item=lost, claimant=claimant,
        status='SUBMITTED', statement='只在授权材料区展示的核验特征SECRET')
    client = authenticated_client(assistant_domain)
    response = client.post('/api/v1/assistant/agent/actions/', dict(action='decide', confirmed=True,
        key=str(uuid.uuid4()), payload=dict(claim_id=str(claim.pk), decision='NEEDS_INFO', note='请补充盒盖特征')), format='json')
    assert response.status_code == 200, response.data
    assert response.data['data']['claim']['status'] == 'NEEDS_INFO'
    assert 'SECRET' not in str(response.data)
    client.force_authenticate(claimant)
    response = client.post('/api/v1/assistant/agent/actions/', dict(action='decide', confirmed=True,
        key=str(uuid.uuid4()), payload=dict(claim_id=str(claim.pk), decision='APPROVE', note='不能自行批准')), format='json')
    assert response.status_code == 403
    client.force_authenticate(unrelated)
    response = client.post('/api/v1/assistant/agent/actions/', dict(action='status', payload=dict(claim_id=str(claim.pk))), format='json')
    assert response.status_code == 404
