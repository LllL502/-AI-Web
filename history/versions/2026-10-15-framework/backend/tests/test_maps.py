"""高德配置不泄露密钥、代理固定上游及标点隐私回归。"""
import json
from unittest.mock import patch, MagicMock
from urllib.parse import urlparse, parse_qs
import pytest
from django.test import override_settings
from rest_framework.test import APIClient
from apps.stations.models import Campus, School
from tests.test_portal_apis import portal, make_item

pytestmark=[pytest.mark.mysql, pytest.mark.django_db]


@override_settings(AMAP_WEB_KEY='public-key',AMAP_SECURITY_CODE='server-secret')
def test_manual_refresh_bypasses_discovery_cache_and_preserves_verified_record():
    import hashlib
    from django.core.cache import cache
    school=School.objects.create(name='刷新测试大学',code='refresh-test-school')
    original=Campus.objects.create(school=school,name='东校区',code='refresh-east',verification_status='VERIFIED',source_url='https://example.edu/campus')
    cache.set(f'amap-campus-discovery-{school.pk}',True,86400)
    cache.set('amap-campus-pois-'+hashlib.sha256(school.name.encode()).hexdigest(),[{'name':'刷新测试大学东校区','id':'POI1'},{'name':'刷新测试大学西校区','id':'POI2'}],300)
    response=APIClient().post('/api/v1/maps/discover-campuses/',{'school':school.pk,'refresh':True},format='json')
    assert response.status_code==200
    assert school.campuses.count()==2
    assert [campus['name'] for campus in response.data['data']['campuses']]==['东校区']
    directory=APIClient().get('/api/v1/stations/campuses/',{'q':school.name}).data['data']['schools'][0]
    assert [campus['name'] for campus in directory['campuses']]==['东校区']
    original.refresh_from_db()
    assert original.verification_status=='VERIFIED' and original.source_url=='https://example.edu/campus'
    cache.clear()


@override_settings(AMAP_WEB_KEY='public-key',AMAP_SECURITY_CODE='server-secret')
def test_discovery_filters_facilities_deduplicates_and_preserves_placeholder():
    from django.core.cache import cache
    cache.clear()
    school=School.objects.create(name='成都医学院',code='discovery-test-school')
    original=Campus.objects.create(school=school,name='主校区',code='discovery-placeholder',verification_status='UNVERIFIED')
    pois=[{'name':name,'id':f'POI{i}'} for i,name in enumerate(['成都医学院新都校区','成都医学院（新都校区）','成都医学院天回校区','成都医学院(新都校区)(地铁站)','成都医学院第一附属医院','成都医学院新都校区南门','其他学校新都校区'])]
    response=MagicMock();response.read.return_value=json.dumps({'status':'1','pois':pois}).encode();response.__enter__.return_value=response
    opener=MagicMock();opener.open.return_value=response
    client=APIClient()
    with patch('config.maps.build_opener',return_value=opener):
        assert client.post('/api/v1/maps/discover-campuses/',{'school':school.pk},format='json').status_code==409
        assert client.get('/_AMapService/v3/place/text',{'keywords':school.name,'platform':'JS'}).status_code==200
        result=client.post('/api/v1/maps/discover-campuses/',{'school':school.pk},format='json')
        second=client.post('/api/v1/maps/discover-campuses/',{'school':school.pk},format='json')
    assert result.status_code==second.status_code==200
    assert set(school.campuses.values_list('name',flat=True))=={'主校区','新都校区','天回校区'}
    assert opener.open.call_count==1
    assert Campus.objects.get(pk=original.pk).is_active
    assert all(c.verification_status=='UNVERIFIED' for c in school.campuses.all())
    assert 'server-secret' not in json.dumps(result.data)
    cache.clear()


@override_settings(AMAP_WEB_KEY='public-key',AMAP_SECURITY_CODE='server-secret')
def test_unverified_real_school_can_search_without_becoming_verified():
    school=School.objects.create(name='成都医学院',code='test-map-school')
    campus=Campus.objects.create(school=school,name='主校区',code='test-map-campus',verification_status='UNVERIFIED')
    data=APIClient().get('/api/v1/maps/config/',HTTP_X_CAMPUS_ID=str(campus.pk)).data['data']
    assert data['enabled'] and not data['campus']['verified']
    campus.refresh_from_db()
    assert campus.verification_status=='UNVERIFIED'
    assert not campus.source_url


@pytest.mark.django_db
@override_settings(AMAP_WEB_KEY='public-key',AMAP_SECURITY_CODE='server-secret')
def test_config_omits_security_code_and_disables_demo():
    client=APIClient()
    campus=Campus.objects.get(code='xjtu-xingqing')
    response=client.get('/api/v1/maps/config/',HTTP_X_CAMPUS_ID=str(campus.pk))
    assert response.data['data']['enabled']
    assert 'server-secret' not in json.dumps(response.data)
    assert not client.get('/api/v1/maps/config/').data['data']['enabled']


@override_settings(AMAP_WEB_KEY='configured-key',AMAP_SECURITY_CODE='private-code')
def test_proxy_rejects_paths_and_injects_server_credentials():
    client=APIClient()
    assert client.get('/_AMapService/https://evil.example/').status_code==404
    assert client.get('/_AMapService/v3/place/text',{'callback':'alert(1)'}).status_code==400
    response=MagicMock()
    response.read.return_value=b'{"status":"1","pois":[]}'
    response.__enter__.return_value=response
    opener=MagicMock();opener.open.return_value=response
    with patch('config.maps.build_opener',return_value=opener):
        result=client.get('/_AMapService/v3/place/text',{'key':'attacker-key','jscode':'attacker-code','callback':'AMap._jsonp1'})
    assert result.status_code==200
    assert result.content.startswith(b'AMap._jsonp1(')
    url=opener.open.call_args[0][0].full_url
    assert urlparse(url).netloc=='restapi.amap.com'
    params=parse_qs(urlparse(url).query)
    assert params['key']==['configured-key']
    assert params['jscode']==['private-code']
    assert b'private-code' not in result.content


@override_settings(AMAP_WEB_KEY='',AMAP_SECURITY_CODE='')
def test_missing_credentials_proxy_returns_unavailable():
    assert APIClient().get('/_AMapService/v3/place/text').status_code==503


@pytest.mark.django_db
def test_point_coordinate_validation_and_public_redaction(portal):
    item=make_item(portal,latitude=34,longitude=108,coordinate_system='GCJ02')
    public=APIClient().get(f'/api/v1/items/{item.pk}/').data['data']
    assert not {'latitude','longitude','coordinate_system'} & set(public)
    client=APIClient();client.force_authenticate(portal['owner'])
    assert client.get(f'/api/v1/items/{item.pk}/').data['data']['coordinate_system']=='GCJ02'
    payload={'kind':'LOST','title':'测试标点','description':'地图选点','category':portal['category'].pk,'location':portal['location'].pk,'occurred_at':item.occurred_at.isoformat(),'latitude':100,'longitude':108,'coordinate_system':'GCJ02'}
    assert client.post('/api/v1/items/',payload,format='json').status_code==400
    payload['latitude']=34
    assert client.post('/api/v1/items/',payload,format='json').status_code==201
    payload['coordinate_system']=''
    assert client.post('/api/v1/items/',payload,format='json').status_code==400
