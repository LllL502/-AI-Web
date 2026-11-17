"""Download official Qwen VoiceDesign weights into this project, with SHA-256."""
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent.parent
DEST=ROOT/'data/local-voice/Qwen3-TTS-12Hz-1.7B-VoiceDesign'
REPO='Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign'

def download(row):
    relative=Path(row['path'])
    path=(DEST/relative).resolve()
    if not path.is_relative_to(DEST.resolve()):raise ValueError('Invalid model path')
    path.parent.mkdir(parents=True,exist_ok=True)
    expected=row.get('lfs',{}).get('oid')
    if path.exists() and path.stat().st_size==row['size']:
        if not expected or hashlib.file_digest(path.open('rb'),'sha256').hexdigest()==expected:
            print(f'Current: {relative}',flush=True);return
    part=path.with_name(path.name+'.part')
    for attempt in range(4):
        offset=part.stat().st_size if part.exists() else 0
        url=f'https://modelscope.cn/models/{REPO}/resolve/master/{row["path"]}'
        request=Request(url,headers={'Range':f'bytes={offset}-'} if offset else {})
        try:
            with urlopen(request,timeout=60) as response:
                append=offset>0 and response.status==206
                with part.open('ab' if append else 'wb') as out:
                    count=offset if append else 0; mark=count
                    while chunk:=response.read(1024*1024):
                        out.write(chunk);count+=len(chunk)
                        if count-mark>=128*1024*1024:
                            print(f'{relative}: {count/1024**2:.0f}/{row["size"]/1024**2:.0f} MiB',flush=True);mark=count
            if part.stat().st_size!=row['size']:raise IOError('Incomplete model file')
            if expected:
                with part.open('rb') as stream: actual=hashlib.file_digest(stream,'sha256').hexdigest()
                if actual!=expected:raise ValueError(f'SHA-256 mismatch: {relative}')
            part.replace(path);print(f'Verified: {relative}',flush=True);return
        except (OSError,TimeoutError) as exc:
            print(f'Retry {relative}: {type(exc).__name__}',flush=True)
            if attempt==3:raise
            time.sleep(1)

if __name__=='__main__':
    DEST.mkdir(parents=True,exist_ok=True)
    with urlopen(f'https://huggingface.co/api/models/{REPO}/tree/main?recursive=true&expand=true',timeout=30) as response:
        rows=[r for r in json.load(response) if r['type']=='file' and not r['path'].startswith('.')]
    (DEST/'download-manifest.json').write_text(json.dumps({'repository':REPO,'source':'Official Qwen model, ModelScope mirror','license':'Apache-2.0','files':rows},ensure_ascii=False,indent=2),encoding='utf8')
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(download,rows))
    print('Local voice model ready.',flush=True)
