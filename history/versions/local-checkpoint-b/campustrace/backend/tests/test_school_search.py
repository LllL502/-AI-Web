"""学校搜索分页与校区联动合同。"""
import pytest
from rest_framework.test import APIClient
from apps.stations.models import School, Campus

pytestmark = pytest.mark.mysql


@pytest.mark.django_db
def test_school_search_initials_and_current_campus():
    school = School.objects.get(code='xjtu')
    school.search_text = '西安交大 xjtu xianjiaotongdaxue xajtdx'
    school.save()
    client = APIClient()
    for term in ['西安交通大学', '西安交大', 'XJTU', 'xajtdx']:
        response = client.get('/api/v1/stations/campuses/', {'q':term})
        assert response.status_code == 200
        assert response.data['data']['schools'][0]['id'] == school.pk
        assert len(response.data['data']['schools'][0]['campuses']) == 4
    campus = school.campuses.first()
    current = client.get('/api/v1/stations/campuses/', {'current_campus':campus.pk})
    assert current.data['data']['total'] == 1


@pytest.mark.django_db
def test_unverified_school_has_no_fabricated_campus_and_search_is_paginated():
    for i in range(25):
        School.objects.create(name=f'分页学校{i:02d}', code=f'page-school-{i}')
    response = APIClient().get('/api/v1/stations/campuses/', {'q':'分页学校'})
    assert response.data['data']['total'] == 25
    assert len(response.data['data']['schools']) == 20
    assert response.data['data']['pages'] == 2
    assert all(not school['campuses'] for school in response.data['data']['schools'])


@pytest.mark.django_db
def test_display_order_is_pinyin_not_enrichment_priority():
    School.objects.create(name='排序浙江大学',code='sort-z',priority=1)
    School.objects.create(name='排序安徽大学',code='sort-a',priority=9)
    result=APIClient().get('/api/v1/stations/campuses/',{'q':'排序'})
    assert [row['name'] for row in result.data['data']['schools']] == ['排序安徽大学','排序浙江大学']
