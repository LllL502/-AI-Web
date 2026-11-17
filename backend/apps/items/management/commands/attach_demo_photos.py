"""Attach reviewed photography references only to missing-photo demo records."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from apps.items.models import Item, MediaAsset
from apps.items.media import process_uploaded_image

class Command(BaseCommand):
 def add_arguments(self,parser):
  parser.add_argument('--apply',action='store_true')
 def handle(self,*args,**options):
  root=Path(__file__).resolve().parents[5]
  folder=root/'data/demo-photos'
  mapping=json.loads((folder/'mapping.json').read_text(encoding='utf8'))
  sources={row['key']:row for row in json.loads((folder/'sources.json').read_text(encoding='utf8'))}
  items=Item.objects.filter(is_demo=True,location__campus__code='demo-campus').select_related('category').prefetch_related('media')
  plan=[]
  for item in items:
   if item.media.exists():continue
   key=mapping.get(item.category.name,{}).get(item.color)
   if not key or (item.category.name=='电脑配件' and 'U 盘' in item.description):continue
   if key=='glasses-blue' and '眼镜盒' not in item.description:continue
   plan.append((item,key))
  self.stdout.write(json.dumps({'total':items.count(),'planned':len(plan),'apply':options['apply']}))
  if not options['apply']:return
  processed={}
  for key in {key for _,key in plan}:
   upload=ContentFile((folder/(key+'.jpg')).read_bytes(),name=key+'.jpg')
   processed[key]=process_uploaded_image(upload)
  manifest=[]
  with transaction.atomic():
   for item,key in plan:
    if item.media.exists():continue
    image=processed[key]
    main=default_storage.save(f'items/demo-reference/{item.pk}/{key}.webp',ContentFile(image.main))
    thumb=default_storage.save(f'items/demo-reference/{item.pk}/{key}-thumb.webp',ContentFile(image.thumbnail))
    asset=MediaAsset.objects.create(item=item,file=main,thumbnail=thumb,sha256=image.digest,width=image.width,height=image.height,is_public=True)
    manifest.append({'item_id':str(item.pk),'asset_id':asset.pk,'file':main,'thumbnail':thumb,'source':sources[key],'usage':'同类实物参考照片，非该失物的现场实拍，不证明具体品牌或核验特征'})
  (root/'artifacts/demo-photo-attachments.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
  self.stdout.write(json.dumps({'attached':len(manifest),'total':items.count(),'with_image':items.filter(media__isnull=False).distinct().count()}))
