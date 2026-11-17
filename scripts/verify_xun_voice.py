"""Generate an original short character audition and measure the actual waveform."""
import base64,io,json,time,wave
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parent.parent
text='嗨，我是小寻！别着急，咱们一起找。你丢了什么呀？'
started=time.monotonic()
request=Request('http://127.0.0.1:11436/speech',data=json.dumps({'text':text}).encode(),headers={'Content-Type':'application/json'})
with urlopen(request,timeout=170) as response:result=json.load(response)
raw=base64.b64decode(result.pop('audio'))
output=ROOT/'artifacts/xun-voice-audition.wav';output.write_bytes(raw)
with wave.open(io.BytesIO(raw)) as audio:
 result.update(channels=audio.getnchannels(),sample_width=audio.getsampwidth(),frames=audio.getnframes(),duration=audio.getnframes()/audio.getframerate())
import numpy as np
samples=np.frombuffer(raw[44:],dtype='<i2').astype(float)/32768
result.update(text=text,total_seconds=round(time.monotonic()-started,2),rms=float(np.sqrt(np.mean(samples**2))),peak=float(np.max(np.abs(samples))),clipped_ratio=float(np.mean(np.abs(samples)>=.999)))
assert result['duration']>2 and result['rms']>.001 and result['clipped_ratio']<.01
(ROOT/'artifacts/xun-voice-audition.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False),flush=True)
