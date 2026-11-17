import uuid
from unittest.mock import patch
import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from apps.items.models import Item
from apps.stations.models import CampusLocation
from tests.test_assistant_workflow import assistant_domain,authenticated_client,isolate_inference_configuration

@pytest.mark.mysql
@pytest.mark.django_db(transaction=True)
def test_card_identity_presence_does_not_reenter_model_or_lose_blue(assistant_domain):
 from apps.assistant.providers import ProviderResult
 from tests.test_assistant_workflow import structured_draft
 d=structured_draft();d.update(category_hint='学生卡',brand='',colors=['蓝色'],location_hint='',public_description='蓝色学生卡',source_spans={'category_hint':'学生卡','colors':'蓝色'},appearance_details=[])
 client=authenticated_client(assistant_domain)
 with patch('apps.assistant.views.converse',return_value={'reply':'你还记得卡面特征吗？','description':'蓝色学生卡','intent':'ask'}),patch('apps.assistant.agent_tools.extract_structured_description',return_value=ProviderResult(payload={'draft':d,'follow_up_questions':[]},provider='test',model='test',simulated=False)):
  first=client.post('/api/v1/assistant/conversation/',{'messages':[{'role':'user','content':'蓝色学生卡'}]},format='json')
 assert first.status_code==200
 with patch('apps.assistant.views.converse',return_value={'description':'有我的名字还有学号等信息','reply':'卡面信息可以留到私密核验，不用发在这里。','intent':'chat','facts_changed':True}) as chat:
  second=client.post('/api/v1/assistant/conversation/',{'context_token':first.data['data']['context_token'],'messages':[{'role':'user','content':'有我的名字还有学号等信息'}]},format='json')
 assert second.status_code==200
 chat.assert_called_once()
 data=second.data['data']
 assert data['draft']['colors']==['蓝色']
 assert data['draft']['identity_markers']==['name','student_number']
 assert '卡面印有姓名、学号信息' in data['description']
 assert '不用发在这里' in data['reply']

@pytest.mark.mysql
@pytest.mark.django_db(transaction=True)
def test_agent_publishes_five_ranked_protected_places_and_rejects_six(assistant_domain):
 locations=[CampusLocation.objects.create(campus=assistant_domain['campus'],parent=assistant_domain['location'],name=f'可能地点{i}',code=f'possible-place-{i}') for i in range(6)]
 ids=[row.pk for row in locations]
 payload={'kind':'LOST','title':'寻找黑色耳机','description':'黑色耳机，盒盖有划痕。','category':assistant_domain['category'].pk,'location':assistant_domain['location'].pk,'occurred_at':timezone.now().isoformat(),'location_candidate_ids':ids[:5]}
 client=authenticated_client(assistant_domain)
 result=client.post('/api/v1/assistant/agent/actions/',{'action':'publish','payload':payload,'confirmed':True,'key':str(uuid.uuid4())},format='json')
 assert result.status_code==200
 item=Item.objects.get(pk=result.data['data']['item']['id'])
 assert list(item.location_candidates.order_by('rank').values_list('location_id','rank'))==list(zip(ids[:5],range(1,6)))
 public=APIClient();public.credentials(HTTP_X_CAMPUS_ID=str(assistant_domain['campus'].pk))
 detail=public.get(f'/api/v1/items/{item.pk}/').data['data']
 assert 'location_candidates' not in detail
 payload['location_candidate_ids']=ids
 assert client.post('/api/v1/assistant/agent/actions/',{'action':'publish','payload':payload,'confirmed':True,'key':str(uuid.uuid4())},format='json').status_code==400
 payload['kind']='FOUND';payload['location_candidate_ids']=ids[:2]
 assert client.post('/api/v1/assistant/agent/actions/',{'action':'publish','payload':payload,'confirmed':True,'key':str(uuid.uuid4())},format='json').status_code==400

def test_actual_identifier_values_are_redacted_but_generic_presence_is_valid():
 from apps.assistant.providers import redact_sensitive_text
 from apps.assistant.identity_features import identity_markers
 assert identity_markers('有我的名字还有学号等信息')==['name','student_number']
 assert '2024123456' not in redact_sensitive_text('学号是2024123456')
 assert identity_markers('没有名字和学号')==[]


@pytest.mark.mysql
@pytest.mark.django_db(transaction=True)
def test_confirmed_found_publication_saves_pickup_place_without_lost_record(assistant_domain):
 place=CampusLocation.objects.create(campus=assistant_domain['campus'],parent=assistant_domain['location'],name='拾获地点',code='found-pickup-place')
 client=authenticated_client(assistant_domain)
 payload={'kind':'FOUND','title':'拾到黑色耳机','description':'黑色耳机，充电盒有划痕。','category':assistant_domain['category'].pk,'location':assistant_domain['location'].pk,'occurred_at':timezone.now().isoformat(),'location_candidate_ids':[place.pk]}
 denied=client.post('/api/v1/assistant/agent/actions/',{'action':'publish','payload':payload,'confirmed':False,'key':str(uuid.uuid4())},format='json')
 assert denied.status_code==400
 assert not Item.objects.filter(title=payload['title']).exists()
 response=client.post('/api/v1/assistant/agent/actions/',{'action':'publish','payload':payload,'confirmed':True,'key':str(uuid.uuid4())},format='json')
 assert response.status_code==200
 item=Item.objects.get(pk=response.data['data']['item']['id'])
 assert item.kind=='FOUND' and item.owner_id==assistant_domain['owner'].pk
 assert list(item.location_candidates.values_list('location_id',flat=True))==[place.pk]
 assert item.media.count()==0
