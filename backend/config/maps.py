"""高德浏览器SDK配置及固定上游安全代理；安全密钥不进入前端或日志。"""
import json
import re
import hashlib
from django.core.cache import cache
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from django.conf import settings
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.throttling import ScopedRateThrottle
from apps.stations.scope import selected_campus
from apps.stations.models import School, Campus, CampusLocation


def campus_candidates(school, pois):
    """只接受完整校名下的校区 POI，附属设施不是独立校区；不声称结果完整。"""
    result={}
    for poi in pois:
        name=poi.get('name','')
        if not name.startswith(school.name) or '校区' not in name:
            continue
        suffix=name[len(school.name):].strip(' ()（）-·')
        if not re.fullmatch(r'[\u4e00-\u9fffA-Za-z0-9·]{1,30}校区',suffix):
            continue
        if any(word in name for word in ('医院','地铁','附属','校门','停车','宿舍')):
            continue
        poi_id=poi.get('id','')
        if not re.fullmatch(r'[A-Za-z0-9]{1,40}',poi_id):
            continue
        result.setdefault(suffix,poi_id)
    return result


class CampusDiscoveryView(APIView):
    permission_classes=[AllowAny]
    throttle_classes=[ScopedRateThrottle]
    throttle_scope='map_proxy'

    def post(self, request):
        try:
            school=School.objects.get(pk=int(request.data.get('school')),is_demo=False)
        except (TypeError,ValueError,School.DoesNotExist):
            raise ValidationError('请选择真实学校')
        cache_key=f'amap-campus-discovery-{school.pk}'
        # 手动刷新消费本轮 SDK 搜索结果，不被一天的自动发现缓存挡住。
        if request.data.get('refresh') is True or not cache.get(cache_key):
            if not settings.AMAP_WEB_KEY or not settings.AMAP_SECURITY_CODE:
                return Response({'error':{'message':'地图服务未配置，暂时保留原校区列表'}},status=503)
            # JS SDK 请求携带其平台参数；只消费服务器代理收到的真实上游响应。
            # 不接收客户端提交的名称/POI，不再拿 JS Key 直接调用 Web 服务。
            pois=cache.get('amap-campus-pois-'+hashlib.sha256(school.name.encode()).hexdigest())
            if pois is None:
                return Response({'error':{'message':'请先完成地图校区搜索，再重试保存候选'}},status=409)
            for name,poi_id in campus_candidates(school,pois).items():
                # 稳定 ID 与按学校去重；不移动占位组已有物品，不冒充官网核实。
                if not Campus.objects.filter(school=school,name=name).exists():
                    code='map-'+hashlib.sha256(f'{school.pk}:{name}'.encode()).hexdigest()[:40]
                    Campus.objects.get_or_create(code=code,defaults={'school':school,'name':name,'verification_status':'UNVERIFIED','source_url':f'https://www.amap.com/detail/{poi_id}'})
            cache.set(cache_key,True,86400)
        campus_queryset=school.campuses.filter(is_active=True)
        # 一旦学校存在正式目录，地图发现项只进入内部候选层，不进入用户选择器。
        if campus_queryset.filter(verification_status='VERIFIED').exists():
            campus_queryset=campus_queryset.filter(verification_status='VERIFIED')
        campuses=list(campus_queryset.values('id','name','verification_status','source_url'))
        return Response({'data':{'campuses':campuses,'notice':'地图候选不保证覆盖全部校区，名称和归属仍需核实。'}})


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class MapConfigView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        campus=Campus.objects.select_related('school').get(pk=selected_campus(request))
        configured=bool(settings.AMAP_WEB_KEY and settings.AMAP_SECURITY_CODE)
        return Response({'data':{
            # 资料核实状态不等于地图可搜索状态；占位校区也可按真实学校检索。
            'enabled':configured and not campus.school.is_demo,
            'web_key':settings.AMAP_WEB_KEY if configured else '',
            'service_host':'/_AMapService',
            'campus':{'id':campus.pk,'name':campus.name,'school':campus.school.name,'city':campus.school.city,'is_demo':campus.school.is_demo,'verified':campus.verification_status=='VERIFIED'},
            'notice':'演示校区使用虚拟布局，不提供真实坐标标点。' if campus.school.is_demo else ('地图服务未配置，请配置高德 Key 和安全密钥并重启后端。' if not configured else ''),
        }})


class CampusRegionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        campus=Campus.objects.get(pk=selected_campus(request))
        if campus.verification_status!='VERIFIED' and not campus.source_url.startswith('https://www.amap.com/detail/'):
            raise ValidationError('校区尚未核实，不能建立真实地点')
        location,_=CampusLocation.objects.get_or_create(code=f'campus-public-{campus.pk}',defaults={'campus':campus,'name':campus.name})
        return Response({'data':{'id':location.pk,'name':location.name}})


class AMapProxyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'map_proxy'

    def get(self, request, endpoint):
        allowed={'v3/place/text','v3/place/around','v3/place/detail','v3/assistant/inputtips','v3/geocode/geo','v3/geocode/regeo','v4/map/styles'}
        if endpoint not in allowed:
            return Response({'error':{'message':'不支持的地图服务'}},status=404)
        if not settings.AMAP_WEB_KEY or not settings.AMAP_SECURITY_CODE:
            return Response({'error':{'message':'地图服务未配置'}},status=503)
        if len(request.META.get('QUERY_STRING',''))>8192:
            return Response({'error':{'message':'地图查询过长'}},status=400)
        params={key:value for key,value in request.query_params.items() if key not in {'key','jscode','callback'}}
        callback=request.query_params.get('callback','')
        if callback and not re.fullmatch(r'[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*',callback):
            return Response({'error':{'message':'无效地图回调'}},status=400)
        params.update(key=settings.AMAP_WEB_KEY,jscode=settings.AMAP_SECURITY_CODE)
        host='https://webapi.amap.com/' if endpoint=='v4/map/styles' else 'https://restapi.amap.com/'
        try:
            with build_opener(NoRedirect).open(Request(host+endpoint+'?'+urlencode(params)),timeout=8) as upstream:
                body=upstream.read(2_000_001)
            if len(body)>2_000_000:
                raise ValueError('oversize')
            payload=json.loads(body)
            safe=json.dumps(payload,ensure_ascii=False)
            if settings.AMAP_SECURITY_CODE in safe:
                raise ValueError('sensitive response')
            keyword=request.query_params.get('keywords','').strip()
            if endpoint=='v3/place/text' and payload.get('status')=='1' and keyword and isinstance(payload.get('pois'),list):
                # 只为数据库内学校的完整名称缓存，避免任意浏览器数据入库。
                if School.objects.filter(name=keyword,is_demo=False).exists():
                    cache_key='amap-campus-pois-'+hashlib.sha256(keyword.encode()).hexdigest()
                    old=cache.get(cache_key,[])
                    cache.set(cache_key,(old+payload['pois'])[-100:],300)
            return HttpResponse(f'{callback}({safe});' if callback else safe,content_type='application/javascript; charset=utf-8' if callback else 'application/json; charset=utf-8')
        except (HTTPError,URLError,TimeoutError,ValueError,OSError):
            return Response({'error':{'message':'地图上游服务暂不可用，请稍后重试'}},status=502)
