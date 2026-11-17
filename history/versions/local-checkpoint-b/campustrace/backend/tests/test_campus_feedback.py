"""反馈不会直接改目录，只有管理员核查后才能采纳。"""
import pytest
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.stations.models import School, Campus, CampusFeedback
from apps.administration.models import AuditLog

pytestmark = pytest.mark.mysql


@pytest.mark.django_db
def test_feedback_requires_login_and_admin_approval_with_source():
    school=School.objects.create(name='反馈学校',code='feedback-school')
    user=User.objects.create_user('feedback-user',password='SafePassword!2026',display_name='用户')
    admin=User.objects.create_user('feedback-admin',password='SafePassword!2026',display_name='管理',role='ADMIN')
    client=APIClient()
    path='/api/v1/stations/campus-feedback/'
    payload={'school':school.pk,'campus_name':'东校区','detail':'官网有东校区介绍','source_url':'https://example.edu.cn/campus'}
    assert client.post(path,payload,format='json').status_code==403
    client.force_authenticate(user)
    result=client.post(path,payload,format='json')
    assert result.status_code==201
    assert not Campus.objects.filter(school=school).exists()
    review='/api/v1/stations/campus-feedback/review/'
    assert client.get(review).status_code==403
    client.force_authenticate(admin)
    data={'id':result.data['data']['id'],'decision':'APPROVE'}
    assert client.post(review,data,format='json').status_code==400
    data['source_url']='https://example.edu.cn/verified'
    assert client.post(review,data,format='json').status_code==200
    assert Campus.objects.get(school=school).verification_status=='VERIFIED'
    assert CampusFeedback.objects.get(pk=data['id']).status=='APPROVED'
    assert AuditLog.objects.filter(action='campus_feedback.approve').exists()
    assert client.post(review,data,format='json').status_code==400


@pytest.mark.django_db
def test_unverified_fallback_is_explicit_and_isolated():
    school=School.objects.create(name='未核实学校',code='fallback-school',priority=3)
    campus=Campus.objects.create(school=school,name='主校区',code='fallback-campus',verification_status='UNVERIFIED')
    result=APIClient().get('/api/v1/stations/campuses/',{'q':'未核实学校'})
    entry=result.data['data']['schools'][0]
    assert entry['campuses'][0]['verification_status']=='UNVERIFIED'
    scoped=APIClient().get('/api/v1/items/',HTTP_X_CAMPUS_ID=str(campus.pk))
    assert scoped.data['data']['total']==0
