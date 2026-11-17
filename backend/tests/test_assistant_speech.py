import base64
from unittest.mock import patch
import pytest
from rest_framework.test import APIClient
from apps.assistant.models import AIJob
from tests.test_assistant_workflow import assistant_domain, authenticated_client

pytestmark=pytest.mark.mysql


def test_unready_voice_never_unloads_dialogue_model():
    import io
    from apps.assistant.speech import generate_speech
    from apps.assistant.providers import ProviderUnavailable
    with patch('apps.assistant.speech.build_opener') as opener, patch('apps.assistant.speech.local_call') as unload:
        opener.return_value.open.return_value=io.BytesIO(b'{"ready":false,"loading":true}')
        with pytest.raises(ProviderUnavailable):
            generate_speech('小寻来帮你找啦！')
        unload.assert_not_called()

@pytest.mark.django_db(transaction=True)
def test_voice_requires_login_and_valid_short_text(assistant_domain):
    assert APIClient().post('/api/v1/assistant/speech/', {'text':'你好'}, format='json').status_code in (401,403)
    client=authenticated_client(assistant_domain)
    with patch('apps.assistant.speech.generate_speech') as generate:
        result=client.post('/api/v1/assistant/speech/', {'text':'长'*81}, format='json')
        assert result.status_code==400
        generate.assert_not_called()

@pytest.mark.django_db(transaction=True)
def test_voice_is_not_persisted_or_replayed(assistant_domain):
    client=authenticated_client(assistant_domain)
    with patch('apps.assistant.speech.generate_speech',return_value={'audio':'UklGRg==','mime':'audio/wav'}) as generate:
        result=client.post('/api/v1/assistant/speech/', {'text':'嗨，咱们一起找！'}, format='json',HTTP_IDEMPOTENCY_KEY='voice-once')
        assert result.status_code==200
        job=AIJob.objects.get()
        assert job.response is None
        assert '咱们' not in job.fingerprint
        replay=client.post('/api/v1/assistant/speech/', {'text':'嗨，咱们一起找！'}, format='json',HTTP_IDEMPOTENCY_KEY='voice-once')
        assert replay.status_code==409
        assert generate.call_count==1
