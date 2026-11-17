import io
from unittest.mock import patch
from django.test import override_settings
from django.core.cache import cache
from apps.assistant.health import model_health


@override_settings(AI_LOCAL_VISION_URL='http://127.0.0.1:11435/v1', AI_LOCAL_VISION_MODEL='vision',
    AI_LOCAL_EMBEDDING_URL='http://127.0.0.1:11435/v1', AI_LOCAL_EMBEDDING_MODEL='absent', AI_PROVIDER_MODE='development_stub')
def test_health_distinguishes_running_service_and_missing_model():
    cache.delete('assistant-health-v2')

    with patch('apps.assistant.health.build_opener') as opener:
        opener.return_value.open.side_effect = [io.BytesIO(b'{"data":[{"id":"vision"}]}'), io.BytesIO(b'{"ready":true,"busy":false,"loaded":false}')]
        result = model_health()
        assert result['models']['vision']['state'] == 'available'
        assert result['models']['embedding']['state'] == 'model_missing'
        assert result['models']['extraction']['state'] == 'simulated'
        assert result['inference_tested'] is False
        assert opener.return_value.open.call_count == 2
        assert result['models']['voice']['ready'] is True
        assert result['ready'] is False
    cache.delete('assistant-health-v2')


@override_settings(AI_LOCAL_VISION_URL='', AI_LOCAL_EMBEDDING_URL='', AI_PROVIDER_MODE='development_stub')
def test_voice_preloading_is_not_reported_as_ready():
    cache.delete('assistant-health-v2')
    with patch('apps.assistant.health.build_opener') as opener:
        opener.return_value.open.return_value = io.BytesIO(b'{"ready":false,"loading":true}')
        result = model_health()
    assert result['models']['voice'] == {'state':'starting','ready':False,'loaded':False,'busy':False}
    assert not result['ready']
    cache.delete('assistant-health-v2')
