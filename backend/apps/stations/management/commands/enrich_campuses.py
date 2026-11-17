"""优先补录重点学校；未核实主校区仅为隔离容器，不是校区事实。"""
import hashlib
import json
from pathlib import Path
from datetime import date
from urllib.parse import urlparse
from django.conf import settings
from django.db import transaction
from django.core.management.base import BaseCommand, CommandError
from apps.stations.models import School, Campus

C9 = '北京大学 清华大学 复旦大学 上海交通大学 浙江大学 南京大学 中国科学技术大学 哈尔滨工业大学 西安交通大学'.split()
OTHER985 = '中国人民大学 北京师范大学 北京航空航天大学 北京理工大学 中国农业大学 中央民族大学 南开大学 天津大学 大连理工大学 东北大学 吉林大学 同济大学 华东师范大学 东南大学 厦门大学 山东大学 中国海洋大学 武汉大学 华中科技大学 湖南大学 中南大学 中山大学 华南理工大学 四川大学 重庆大学 电子科技大学 西北工业大学 西北农林科技大学 兰州大学 国防科技大学'.split()
OTHER211 = '北京交通大学 北京工业大学 北京科技大学 北京化工大学 北京邮电大学 北京林业大学 北京中医药大学 北京外国语大学 中国传媒大学 中央财经大学 对外经济贸易大学 北京体育大学 中央音乐学院 中国政法大学 华北电力大学 天津医科大学 河北工业大学 太原理工大学 内蒙古大学 辽宁大学 大连海事大学 延边大学 东北师范大学 哈尔滨工程大学 东北农业大学 东北林业大学 华东理工大学 东华大学 上海外国语大学 上海财经大学 上海大学 苏州大学 南京航空航天大学 南京理工大学 中国矿业大学 河海大学 江南大学 南京农业大学 中国药科大学 南京师范大学 安徽大学 合肥工业大学 福州大学 南昌大学 郑州大学 武汉理工大学 华中农业大学 华中师范大学 中南财经政法大学 湖南师范大学 暨南大学 华南师范大学 广西大学 海南大学 西南交通大学 四川农业大学 西南财经大学 西南大学 贵州大学 云南大学 西藏大学 西北大学 西安电子科技大学 长安大学 陕西师范大学 青海大学 宁夏大学 新疆大学 石河子大学 中国矿业大学（北京） 中国地质大学（北京） 中国地质大学（武汉） 中国石油大学（北京） 中国石油大学（华东）'.split()


class Command(BaseCommand):
    help = '补录有官网来源的校区并创建明确未核实的默认主校区'

    @transaction.atomic
    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR).parent
        data = json.loads((root/'data/schools/verified-campuses.json').read_text(encoding='utf-8'))
        for supplement in sorted((root/'data/schools').glob('verified-campuses-*.json')):
            extra=json.loads(supplement.read_text(encoding='utf-8'))
            data['schools'].extend(extra['schools'])
        # 将数据补录目标独立保存，避免把“有一条校区”误称为“完整校区名单”。
        other_key = json.loads((root/'data/schools/verified-campuses-other-key.json').read_text(encoding='utf-8'))
        expanded = json.loads((root/'data/schools/verified-campuses-expanded.json').read_text(encoding='utf-8'))
        local = json.loads((root/'data/schools/verified-campuses-local.json').read_text(encoding='utf-8'))
        for row in data['schools']:
            hostname = urlparse(row['source']).hostname or ''
            if not hostname.endswith('.edu.cn') or not row['campuses']:
                raise CommandError(f"缺少学校官网来源或校区记录：{row['school']}")
        for priority, names in [(1,C9),(2,OTHER985),(3,OTHER211)]:
            School.objects.filter(name__in=names).update(priority=priority)
        for row in data['schools']:
            if row.get('create_school'):
                School.objects.get_or_create(name=row['school'],defaults={'code':row['school_code'],'source_url':row['source'],'priority':2 if row['school']=='国防科技大学' else 3,'level':'本科'})
            school = School.objects.get(name=row['school'], is_demo=False)
            for name in row['campuses']:
                code = 'verified-' + hashlib.sha256(f'{school.pk}:{name}'.encode()).hexdigest()[:24]
                campus = Campus.objects.filter(school=school,name=name).first()
                if campus is None:
                    campus = Campus(school=school,name=name,code=code)
                campus.verification_status='VERIFIED'
                campus.source_url=row['source']
                campus.verified_at=date.fromisoformat(data['checked_at'])
                campus.save()
            # 保留历史分组和其数据；无地点的默认分组隐藏，避免新用户继续选错。
            Campus.objects.filter(school=school,verification_status='UNVERIFIED',locations__isnull=True).update(is_active=False)
        for school in School.objects.filter(is_demo=False, campuses__isnull=True):
            Campus.objects.create(school=school,name='主校区',code=f'pending-{school.pk}',verification_status='UNVERIFIED')
        verified = Campus.objects.filter(verification_status='VERIFIED',school__is_demo=False)
        target_groups={'985':sorted(set(C9+OTHER985)), 'other_211':sorted(set(OTHER211+['海军军医大学','空军军医大学'])), 'other_key':sorted({row['school'] for row in other_key['schools']}), 'expanded':sorted({row['school'] for row in expanded['schools']}), 'local_bachelor':sorted({row['school'] for row in local['schools']})}
        target_status={}
        for key,names in target_groups.items():
            missing=[name for name in names if not verified.filter(school__name=name).exists()]
            target_status[key]={'school_count':len(names),'covered':len(names)-len(missing),'missing':missing,'names':names}
        evidence = {'checked_at':data['checked_at'], 'verified_campuses':verified.count(), 'verified_schools':verified.values('school_id').distinct().count(), 'fallback_campuses':Campus.objects.filter(verification_status='UNVERIFIED',is_active=True).count(), 'retained_inactive_fallbacks':Campus.objects.filter(verification_status='UNVERIFIED',is_active=False).count(), 'target_groups':target_status, 'priority_counts':{str(i):School.objects.filter(priority=i).count() for i in [1,2,3,9]}, 'scope_note':data['scope_note'], 'priority_note':'C9/985/211仅为资料补录顺序，页面按拼音A-Z展示。军队院校由官网独立补充，无教育部普通高校标识码；华北电力北京/保定作为一所学校两个校区，不重复建校。覆盖是每校至少一条有来源的校区/校园/校本部记录，不是全部校区完整性认证。'}
        (root/'data/schools/campus-coverage.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if any(group['missing'] for group in target_status.values()):
            raise CommandError('目标学校仍有缺口，详见campus-coverage.json')
        self.stdout.write(f'Verified campus/area records: {verified.count()}; schools: {verified.values("school_id").distinct().count()}; active fallback: {evidence["fallback_campuses"]}')
