"""Resumable ranged download of the Windows CUDA wheel, verified against its official hash."""
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / 'tools/voice-wheels'
NAME = 'torch-2.6.0+cu124-cp312-cp312-win_amd64.whl'
URL = 'https://mirrors.aliyun.com/pytorch-wheels/cu124/' + NAME.replace('+', '%2B')
SIZE = 2532302369
CHUNK = 8 * 1024 * 1024


def part(index):
    start = index * CHUNK
    end = min(SIZE, start + CHUNK) - 1
    path = DEST / f'torch-cu124.part-{index:04d}'
    if path.exists() and path.stat().st_size == end-start+1:
        return path
    for attempt in range(8):
        try:
            request = Request(URL + f'?chunk={index}', headers={'Range': f'bytes={start}-{end}'})
            with urlopen(request, timeout=40) as response:
                if response.status != 206 or not response.headers.get('Content-Range', '').startswith(f'bytes {start}-{end}/'):
                    raise OSError('Range mismatch')
                data = response.read(end-start+2)
            if len(data) != end-start+1:
                raise OSError('Short chunk')
            path.write_bytes(data)
            if index % 16 == 0:
                print(f'Runtime chunk {index}/{(SIZE+CHUNK-1)//CHUNK}', flush=True)
            return path
        except OSError:
            if attempt == 7:
                raise
            time.sleep(1)


if __name__ == '__main__':
    DEST.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=16) as pool:
        paths = list(pool.map(part, range((SIZE+CHUNK-1)//CHUNK)))
    wheel = DEST / NAME
    with wheel.open('wb') as out:
        for path in paths:
            out.write(path.read_bytes())
    with wheel.open('rb') as source:
        checksum = hashlib.file_digest(source, 'sha256').hexdigest()
    if checksum != '3313061c1fec4c7310cf47944e84513dcd27b6173b72a349bb7ca68d0ee6e9c0':
        raise ValueError('Runtime differs from the official PyTorch SHA-256')
    (DEST / 'runtime-download.json').write_text(json.dumps({'source': URL, 'sha256': checksum,
        'size': wheel.stat().st_size, 'official_index': 'https://download.pytorch.org/whl/cu124/torch/'}, indent=2))
    print(f'Runtime assembled: {checksum}', flush=True)
