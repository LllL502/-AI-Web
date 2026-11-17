from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from tests.test_workflows import domain, item, lost_item
from apps.accounts.models import User
from apps.administration.serializers import AdminUserSerializer
from apps.claims.models import ActiveReservation, Claim, HandoverAppointment
from apps.claims.services import decide_claim, submit_claim, start_direct_handover, confirm_direct_handover, schedule_handover
from apps.items.models import Item
from apps.items.serializers import ItemSerializer
from apps.matching.models import AlgorithmConfig, MatchRun
from apps.matching.services import execute_match_run

pytestmark = [pytest.mark.mysql, pytest.mark.django_db(transaction=True)]


def test_suspension_blocks_existing_authenticated_session(domain):
    user = domain['claimant']
    client = APIClient()
    client.force_login(user)
    assert client.get('/api/v1/auth/me/').status_code == 200
    serializer = AdminUserSerializer(user, data={'account_status': 'SUSPENDED'}, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    assert client.get('/api/v1/auth/me/').status_code == 403


def test_demoted_staff_cannot_read_sensitive_item(domain):
    user = domain['staff']
    user.role = User.Role.USER
    user.save()
    data = ItemSerializer(item(domain), context={'request': SimpleNamespace(user=user)}).data
    assert 'location_detail' not in data
    assert 'latitude' not in data


def test_old_claim_cannot_reserve_returned_item(domain):
    found = item(domain)
    claim = submit_claim(found, domain['claimant'], '特征', {}, lost_item(domain, domain['claimant']))
    Item.objects.filter(pk=found.pk).update(business_status=Item.BusinessStatus.RETURNED)
    with pytest.raises(ValidationError):
        decide_claim(claim, domain['staff'], 'APPROVE', '')
    assert not ActiveReservation.objects.exists()
    found.refresh_from_db()
    assert found.business_status == Item.BusinessStatus.RETURNED


def test_wrong_code_count_survives_api_error(domain):
    found = item(domain)
    claim = submit_claim(found, domain['claimant'], '特征', {}, lost_item(domain, domain['claimant']))
    decide_claim(claim, domain['staff'], 'APPROVE', '')
    appointment, code = schedule_handover(claim, domain['claimant'], domain['station'], timezone.now() + timedelta(hours=1))
    client = APIClient()
    client.force_login(domain['claimant'])
    for count in range(1, 6):
        response = client.post(f'/api/v1/claims/{claim.pk}/handover/verify/', {'code': 'wrong'}, format='json')
        assert response.status_code == 400
        appointment.refresh_from_db()
        assert appointment.failed_attempts == count
    assert client.post(f'/api/v1/claims/{claim.pk}/handover/verify/', {'code': code}, format='json').status_code == 400


def test_station_custody_rejects_direct_handover_and_confirmation(domain):
    found = item(domain)
    claim = submit_claim(found, domain['claimant'], '特征', {}, lost_item(domain, domain['claimant']))
    decide_claim(claim, domain['staff'], 'APPROVE', '')
    with pytest.raises(ValidationError):
        start_direct_handover(claim, domain['claimant'])
    Claim.objects.filter(pk=claim.pk).update(status=Claim.Status.HANDOVER_PENDING, handover_method=Claim.HandoverMethod.DIRECT)
    with pytest.raises(ValidationError):
        confirm_direct_handover(claim, domain['claimant'])


def test_station_member_delete_route_is_enabled(domain):
    admin = User.objects.create_user('admin-regression', role=User.Role.ADMIN, display_name='管理员')
    client = APIClient()
    client.force_authenticate(admin)
    membership = domain['staff'].station_memberships.get()
    response = client.delete(f'/api/v1/admin/stations/{domain["station"].pk}/members/', {'membership_id': membership.pk}, format='json')
    assert response.status_code == 200
    assert not domain['staff'].station_memberships.exists()
    assert client.delete(f'/api/v1/admin/stations/{domain["station"].pk}/').status_code == 405


@pytest.mark.parametrize('override', [
    {'kind': Item.Kind.FOUND}, {'review_status': Item.ReviewStatus.DRAFT},
    {'business_status': Item.BusinessStatus.RETURNED},
])
def test_claim_rejects_invalid_related_lost_item(domain, override):
    related = lost_item(domain, domain['claimant'])
    Item.objects.filter(pk=related.pk).update(**override)
    with pytest.raises(ValidationError):
        submit_claim(item(domain), domain['claimant'], '特征', {}, related)


@pytest.mark.parametrize('endpoint', ['login', 'register'])
def test_anonymous_auth_requires_csrf(endpoint):
    client = APIClient(enforce_csrf_checks=True)
    assert client.post(f'/api/v1/auth/{endpoint}/', {}, format='json').status_code == 403
    token = client.get('/api/v1/auth/csrf/').data['data']['csrf_token']
    assert client.post(f'/api/v1/auth/{endpoint}/', {}, format='json', HTTP_X_CSRFTOKEN=token).status_code == 400


def test_stale_item_edit_cannot_overwrite_claim_status(domain):
    found = item(domain)
    serializer = ItemSerializer(found, data={'title': 'edited'}, partial=True, context={'request': SimpleNamespace(user=domain['owner'], query_params={}, headers={})})
    serializer.is_valid(raise_exception=True)
    Item.objects.filter(pk=found.pk).update(business_status=Item.BusinessStatus.RESERVED)
    with pytest.raises(ValidationError):
        serializer.save()
    found.refresh_from_db()
    assert found.business_status == Item.BusinessStatus.RESERVED
    assert found.title != 'edited'


def test_concurrent_editor_waits_for_claim_item_lock(domain):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from django.db import close_old_connections, transaction

    found = item(domain)
    ready = Event()

    def edit_from_other_connection():
        close_old_connections()
        try:
            stale = Item.objects.get(pk=found.pk)
            request = SimpleNamespace(user=domain['owner'], query_params={}, headers={})
            serializer = ItemSerializer(stale, data={'title': 'concurrent edit'}, partial=True, context={'request': request})
            serializer.is_valid(raise_exception=True)
            ready.set()
            with pytest.raises(ValidationError):
                serializer.save()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            locked = Item.objects.select_for_update().get(pk=found.pk)
            worker = pool.submit(edit_from_other_connection)
            assert ready.wait(timeout=10)
            locked.business_status = Item.BusinessStatus.RESERVED
            locked.save(update_fields=['business_status'])
        worker.result(timeout=10)
    found.refresh_from_db()
    assert found.business_status == Item.BusinessStatus.RESERVED
    assert found.title != 'concurrent edit'


def test_failed_matching_run_survives_database_write_failure(domain):
    from apps.matching.engine import DEFAULT_WEIGHTS
    AlgorithmConfig.objects.create(name='test', version='security-test', weights=DEFAULT_WEIGHTS, thresholds={}, preprocessing={}, is_published=True, published_at=timezone.now(), created_by=domain['staff'])
    query = lost_item(domain, domain['claimant'])
    item(domain, occurred_at=query.occurred_at + timedelta(minutes=1))
    client = APIClient()
    client.force_login(domain['claimant'])
    client.raise_request_exception = False
    with patch('apps.matching.services.MatchCandidate.objects.bulk_create', side_effect=IntegrityError('simulated write failure')):
        response = client.post('/api/v1/matches/runs/', {'query_item_id': str(query.pk)}, format='json')
    assert response.status_code == 500
    run = MatchRun.objects.get(query_item=query)
    assert run.status == MatchRun.Status.FAILED
    assert run.error_code == 'matching_failed'
    assert run.candidates.count() == 0
