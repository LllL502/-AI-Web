import json
from urllib.parse import urlparse
from urllib.request import Request, build_opener, ProxyHandler
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from .local_models import NoRedirect


def model_health():
    cached = cache.get('assistant-health-v2')
    if cached is not None:
        return cached
    results, probes = {}, {}
    for name, base, model in [
        ('vision', settings.AI_LOCAL_VISION_URL, settings.AI_LOCAL_VISION_MODEL),
        ('embedding', settings.AI_LOCAL_EMBEDDING_URL, settings.AI_LOCAL_EMBEDDING_MODEL),
        ('extraction', settings.AI_PROVIDER_BASE_URL if settings.AI_PROVIDER_MODE == 'openai_compatible' else '', settings.AI_PROVIDER_MODEL),
    ]:
        if name == 'extraction' and settings.AI_PROVIDER_MODE == 'development_stub':
            results[name] = {'state': 'simulated', 'ready': False}
            continue
        if not base or not model:
            results[name] = {'state': 'not_configured', 'ready': False}
            continue
        parsed = urlparse(base)
        if parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
            results[name] = {'state': 'not_probed', 'ready': False}
            continue
        if base not in probes:
            try:
                request = Request(base.rstrip('/')+'/models', headers={'Accept': 'application/json'})
                with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=2) as response:
                    payload = response.read(1024*1024+1)
                if len(payload) > 1024*1024:
                    raise ValueError()
                probes[base] = {row['id'] for row in json.loads(payload)['data']}
            except (OSError, ValueError, KeyError, TypeError):
                probes[base] = None
        registered = probes[base]
        state = 'unavailable' if registered is None else 'available' if model in registered else 'model_missing'
        results[name] = {'state': state, 'ready': state == 'available'}
    try:
        request = Request('http://127.0.0.1:11436/health', headers={'Accept':'application/json'})
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=2) as response:
            voice = json.loads(response.read(16384))
        state = 'available' if voice.get('ready') is True else 'starting' if voice.get('loading') is True else 'model_missing'
        results['voice'] = {'state':state,'ready':state=='available','loaded':voice.get('loaded') is True,'busy':voice.get('busy') is True}
    except (OSError, ValueError, TypeError, AttributeError):
        results['voice'] = {'state':'unavailable','ready':False}
    output = {'checked_at': timezone.now().isoformat(), 'models': results,
        'ready': all(row['ready'] for row in results.values()),
        'inference_tested': False, 'max_concurrent': settings.AI_MAX_CONCURRENT,
        'total_timeout_seconds': settings.AI_TOTAL_TIMEOUT_SECONDS}
    cache.set('assistant-health-v2', output, 15)
    return output
