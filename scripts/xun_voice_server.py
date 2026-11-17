"""Loopback-only neural character voice. Run with tools/qwen-tts-env Python."""
import base64
import io
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / 'data/local-voice/Qwen3-TTS-12Hz-1.7B-VoiceDesign'
STYLE = ('清亮、活泼、可爱的中文小女孩童声，像机灵温暖的小伙伴在面对面聊天。'
         '音色柔软明亮，语气有好奇心和亲切的笑意，句尾自然上扬，轻快但不抢话。'
         '根据句意自然停顿和重读，有自然的呼吸和语调变化。不要播音腔，不要逐字朗读，不要夸张尖叫。')
lock = threading.Lock()
model = None
load_error = None
loading = threading.Event()


def load_model():
    """Load CPU weights before declaring readiness; never reserve the shared GPU."""
    global model, load_error
    try:
        import torch
        from qwen_tts import Qwen3TTSModel
        model = Qwen3TTSModel.from_pretrained(str(MODEL), device_map='cpu',
            dtype=torch.bfloat16, attn_implementation='sdpa', local_files_only=True)
    except Exception as exc:
        load_error = type(exc).__name__
        print(f'Voice initialization failed: {load_error}', flush=True)
    finally:
        loading.set()


def synthesize(text):
    import torch
    import soundfile as sf
    global model
    if model is None:
        raise RuntimeError('Voice model is still preparing or failed to initialize')
    started = time.monotonic()
    try:
        model.model.to('cuda:0')
        model.device = torch.device('cuda:0')
        model.model.speech_tokenizer.model.to('cuda:0')
        model.model.speech_tokenizer.device = torch.device('cuda:0')
        # Keep the synthetic character consistent between utterances.
        torch.manual_seed(926)
        with torch.inference_mode():
            waves, rate = model.generate_voice_design(text=text, language='Chinese',
                instruct=STYLE, max_new_tokens=360, max_time=65, do_sample=True,
                top_p=.9, temperature=.8)
        buffer = io.BytesIO()
        sf.write(buffer, waves[0], rate, format='WAV', subtype='PCM_16')
        return {'audio': base64.b64encode(buffer.getvalue()).decode(), 'mime': 'audio/wav',
            'sample_rate': rate, 'duration': len(waves[0])/rate,
            'generation_seconds': round(time.monotonic()-started, 2), 'voice': 'xun-child-v1'}
    finally:
        # Leave the laptop GPU available for the vision and search models.
        model.model.to('cpu')
        model.device = torch.device('cpu')
        model.model.speech_tokenizer.model.to('cpu')
        model.model.speech_tokenizer.device = torch.device('cpu')
        torch.cuda.empty_cache()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Never log users' speech text.

    def reply(self, status, payload):
        data = json.dumps(payload).encode()
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        if self.path != '/health':
            return self.reply(404, {'error': 'not_found'})
        self.reply(200, {'ready': model is not None and load_error is None,
            'loading':not loading.is_set(), 'error':load_error,
            'loaded': model is not None, 'busy': lock.locked(), 'voice': 'xun-child-v1'})

    def do_POST(self):
        if self.path != '/speech':
            return self.reply(404, {'error': 'not_found'})
        if self.headers.get('Origin') or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.reply(403, {'error': 'backend_only'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096:
                raise ValueError()
            text = json.loads(self.rfile.read(size)).get('text', '').strip()
            if not isinstance(text, str) or not 1 <= len(text) <= 80:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            return self.reply(400, {'error': 'invalid_text'})
        if model is None:
            return self.reply(503, {'error':'voice_preparing' if not loading.is_set() else 'voice_initialization_failed'})
        if not lock.acquire(blocking=False):
            return self.reply(429, {'error': 'voice_busy'})
        try:
            self.reply(200, synthesize(text))
        except Exception as exc:
            print(f'Voice generation failed: {type(exc).__name__}: {exc}', flush=True)
            self.reply(503, {'error': 'voice_unavailable'})
        finally:
            lock.release()


if __name__ == '__main__':
    print('Xun neural voice: http://127.0.0.1:11436', flush=True)
    threading.Thread(target=load_model, daemon=True).start()
    ThreadingHTTPServer(('127.0.0.1', 11436), Handler).serve_forever()
