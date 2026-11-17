import json, urllib.request, concurrent.futures
from pathlib import Path
root=Path(__file__).resolve().parents[1]
folder=root/'data/demo-photos'
def download(row):
 path=folder/(row['key']+'.jpg')
 if path.exists():return row['key']+' cached'
 req=urllib.request.Request(row['url'],headers={'User-Agent':'CampusTrace-demo-assets/1.0'})
 with urllib.request.urlopen(req,timeout=45) as response: raw=response.read()
 if len(raw)>5*1024*1024:raise ValueError('Oversized image')
 from PIL import Image
 from io import BytesIO
 Image.open(BytesIO(raw)).verify()
 path.write_bytes(raw)
 return row['key']+' downloaded'
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  for result in pool.map(download,json.loads((folder/'sources.json').read_text(encoding='utf8'))):print(result,flush=True)
