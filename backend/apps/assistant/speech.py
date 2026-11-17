"""Authenticated local speech; no audio or raw text is persisted."""
import base64
import json
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler

from django.conf import settings
from rest_framework import serializers
from .local_models import NoRedirect, local_call
from .providers import ProviderUnavailable, ProviderProtocolError
from .runtime import check_budget


class SpeechInput(serializers.Serializer):
    text = serializers.CharField(max_length=80, trim_whitespace=True)


def generate_speech(text):
    # Only this public, fixed greeting is bundled. Personal replies are never cached.
    if text == '嗨，我是小寻！别着急，咱们一起找。你丢了什么呀？':
        greeting = Path(__file__).resolve().parents[3] / 'frontend/public/audio/xun-greeting.wav'
        if greeting.is_file():
            return {'audio': base64.b64encode(greeting.read_bytes()).decode(),
                'mime': 'audio/wav', 'voice': 'xun-child-v1'}
    try:
        request = Request('http://127.0.0.1:11436/health', headers={'Accept':'application/json'})
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=check_budget(2)) as response:
            health = json.loads(response.read(16384))
        if health.get('ready') is not True:
            raise ProviderUnavailable('小寻的声音正在准备，请稍后再试。')
    except (OSError, ValueError, AttributeError):
        raise ProviderUnavailable('小寻的语音服务未启动，请检查服务状态。') from None
    # All AI requests share the admission lock. Release idle Ollama weights
    # before loading the voice on an 8GB laptop GPU.
    for url, name in {(settings.AI_LOCAL_VISION_URL, settings.AI_LOCAL_VISION_MODEL),
                      (settings.AI_LOCAL_EMBEDDING_URL, settings.AI_LOCAL_EMBEDDING_MODEL)}:
        if url and name:
            base = url.rstrip('/').removesuffix('/v1')
            local_call(base, '/api/generate', {'model': name, 'keep_alive': 0})
    request = Request('http://127.0.0.1:11436/speech',
        data=json.dumps({'text': text}).encode(), headers={'Content-Type': 'application/json'})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=check_budget(85)) as response:
            result = json.loads(response.read(3_000_000))
    except (OSError, ValueError):
        raise ProviderUnavailable('小寻的声音暂未准备好，请稍后再试。') from None
    check_budget()
    try:
        audio = base64.b64decode(result['audio'], validate=True)
        if not audio.startswith(b'RIFF') or audio[8:12] != b'WAVE' or len(audio) > 2_000_000:
            raise ValueError()
        return {'audio': result['audio'], 'mime': 'audio/wav', 'voice': 'xun-child-v1'}
    except (KeyError, TypeError, ValueError):
        raise ProviderProtocolError('小寻的语音生成失败，请重试。') from None
