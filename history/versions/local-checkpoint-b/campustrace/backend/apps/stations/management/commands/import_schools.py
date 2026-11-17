"""解析教育部原始附件，先校验再入库；不创建未经核实的校区。"""
import hashlib
import json
import re
from pathlib import Path
import xlrd
from pypinyin import lazy_pinyin, Style
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.stations.models import School

SOURCE = 'https://www.moe.gov.cn/jyb_xxgk/s5743/s5744/202606/t20260618_1441074.html'


class Command(BaseCommand):
    help = '导入教育部2026普通高校名单（2952所）'

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR).parent
        path = root / 'data/schools/moe-2026-ordinary.xls'
        sheet = xlrd.open_workbook(path).sheet_by_index(0)
        rows = []
        province = ''
        for i in range(3, sheet.nrows):
            row = sheet.row_values(i)
            if not isinstance(row[0], (int, float)):
                if row[0]:
                    province = re.split(r'[（(]', str(row[0]))[0].strip()
                continue
            code = str(int(row[2]))
            name = str(row[1]).strip()
            if len(code) != 10 or not name or not province:
                raise CommandError(f'第{i+1}行格式异常')
            rows.append({'official_id':code, 'name':name, 'province':province, 'city':str(row[4]).strip(), 'level':str(row[5]).strip()})
        if len(rows) != 2952 or len({r['official_id'] for r in rows}) != 2952:
            raise CommandError('官方数量或标识码唯一性校验失败')
        if sum(r['level'] == '本科' for r in rows) != 1412:
            raise CommandError('本科数量校验失败')
        aliases = {'西安交通大学':'西安交大 西交大 xjtu'}
        with transaction.atomic():
            for row in rows:
                name = row['name']
                search = ' '.join([name, ''.join(lazy_pinyin(name)), ''.join(lazy_pinyin(name, style=Style.FIRST_LETTER)), aliases.get(name, '')])
                existing = School.objects.filter(official_id=row['official_id']).first()
                if existing is None:
                    existing = School.objects.filter(name=name, official_id__isnull=True, is_demo=False).first()
                if existing is None:
                    existing = School(code='moe-' + row['official_id'])
                for key, value in row.items():
                    setattr(existing, key, value)
                existing.search_text = search
                existing.source_url = SOURCE
                existing.save()
        evidence = {'source_url':SOURCE, 'source_date':'2026-06-17', 'sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'ordinary_schools':len(rows), 'undergraduate':1412, 'vocational':1540, 'campuses_created':0, 'scope':'普通高校；不包含成人高校及港澳台；校区单独核实'}
        (root / 'data/schools/import-evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('Imported 2952 schools; verified unique IDs; no campuses fabricated.'))
