from unittest.mock import patch
import pytest
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.assistant.dialogue_state import guard_question,unknown_fields
from tests.test_assistant_workflow import assistant_domain,authenticated_client,isolate_inference_configuration,make_item


def test_unknown_location_is_memory_not_a_repeated_required_question():
 fields=unknown_fields([{'role':'user','content':'我不知道在哪里丢的'}],{})
 assert fields==['location']
 result=guard_question({'reply':'那你还记得丢在哪儿吗？','intent':'ask','question_field':'location'},fields)
 assert result['intent']=='search'
 assert '不用猜' in result['reply']
 assert unknown_fields([{'role':'user','content':'不知道'}],{'last_question':'appearance'})==['appearance']

@pytest.mark.mysql
@pytest.mark.django_db(transaction=True)
def test_natural_reply_survives_and_chat_does_not_trigger_search(assistant_domain):
 client=authenticated_client(assistant_domain)
 first={'description':'黑色耳机，盒盖有划痕','reply':'先别着急，你还记得它最后在哪儿用过吗？','intent':'ask','question_field':'location'}
 with patch('apps.assistant.views.converse',return_value=first),patch('apps.assistant.agent_tools.query_public_items') as search:
  result=client.post('/api/v1/assistant/conversation/',{'messages':[{'role':'user','content':'我丢了黑色耳机，盒盖有划痕'}]},format='json')
 assert result.status_code==200
 data=result.data['data'];assert data['reply']==first['reply'];assert data['context_token']
 search.assert_not_called()
 token=data['context_token']
 next_plan={'description':'','reply':'没关系，地点先留空。盒盖上还有贴纸或者挂件吗？','intent':'ask','question_field':'appearance'}
 with patch('apps.assistant.views.converse',return_value=next_plan),patch('apps.assistant.agent_tools.query_public_items') as search:
  second=client.post('/api/v1/assistant/conversation/',{'context_token':token,'messages':[{'role':'user','content':'我不知道在哪里丢的'}]},format='json')
 assert second.status_code==200
 assert second.data['data']['reply']==next_plan['reply']
 assert 'location' in second.data['data']['unavailable_fields']
 assert '黑色耳机' in second.data['data']['description']
 search.assert_not_called()

@pytest.mark.mysql
@pytest.mark.django_db(transaction=True)
def test_memory_cannot_be_forged_or_used_by_another_account(assistant_domain):
 client=authenticated_client(assistant_domain)
 with patch('apps.assistant.views.converse',return_value={'description':'黑色耳机','reply':'你想先找线索吗？','intent':'ask'}):
  first=client.post('/api/v1/assistant/conversation/',{'messages':[{'role':'user','content':'黑色耳机'}]},format='json')
 token=first.data['data']['context_token']
 payload={'context_token':token+'x','messages':[{'role':'user','content':'继续'}]}
 assert client.post('/api/v1/assistant/conversation/',payload,format='json').status_code==400
 other=User.objects.create_user('dialogue-other',password='TestOnly!2026')
 client.force_authenticate(other);payload['context_token']=token
 assert client.post('/api/v1/assistant/conversation/',payload,format='json').status_code==400

@pytest.mark.mysql
@pytest.mark.django_db(transaction=True)
def test_search_reports_only_live_results_and_publication_is_only_prepared(assistant_domain):
 row=make_item(assistant_domain)
 client=authenticated_client(assistant_domain)
 with patch('apps.assistant.views.converse',return_value={'description':'黑色耳机','reply':'好，我先按耳机的外观找找。','intent':'search'}):
  first=client.post('/api/v1/assistant/conversation/',{'messages':[{'role':'user','content':'帮我找黑色耳机'}]},format='json')
 assert first.status_code==200
 data=first.data['data'];assert data['candidates'];assert '这次查到' in data['reply']
 from apps.items.models import Item
 count=Item.objects.count();row.business_status='CLOSED';row.save(update_fields=['business_status'])
 with patch('apps.assistant.views.converse',return_value={'description':'','reply':'我先把发布内容整理出来，你核对后再提交。','intent':'publish'}):
  second=client.post('/api/v1/assistant/conversation/',{'context_token':data['context_token'],'messages':[{'role':'user','content':'帮我发布寻物启事'}]},format='json')
 assert second.status_code==200
 assert second.data['data']['ui_action']['type']=='publish'
 assert second.data['data']['candidates']==[]
 assert Item.objects.count()==count


def test_latest_help_question_does_not_inherit_an_old_search():
 from apps.assistant.dialogue_state import ground_plan
 result=ground_plan({'intent':'search','reply':'当然可以！没有照片也能发布。你还记得在哪里丢的吗？'},[{'role':'user','content':'没有照片也可以发布吗？'}],{})
 assert result['intent']=='chat'
 assert '照片' in result['reply']
 assert '在哪里' not in result['reply']

@pytest.mark.mysql
@pytest.mark.django_db(transaction=True)
def test_workflow_context_is_owned_and_never_contains_private_proof(assistant_domain):
 from apps.claims.models import Claim
 found=make_item(assistant_domain)
 claim=Claim.objects.create(found_item=found,claimant=assistant_domain['owner'],status='SUBMITTED',statement='私密核验编号SECRET-123')
 client=authenticated_client(assistant_domain)
 with patch('apps.assistant.views.converse',return_value={'description':'','reply':'申请已提交，正在等对方核验。','intent':'chat'}) as converse:
  response=client.post('/api/v1/assistant/conversation/',{'messages':[{'role':'user','content':'下一步该怎么办'}],'tool_context':{'claim_id':str(claim.pk)}},format='json')
 assert response.status_code==200
 workflow=converse.call_args.kwargs['memory']['workflow']
 assert workflow['claim_status']=='SUBMITTED'
 assert 'SECRET' not in str(workflow)
 other=User.objects.create_user('workflow-other',password='TestOnly!2026')
 client.force_authenticate(other)
 assert client.post('/api/v1/assistant/conversation/',{'messages':[{'role':'user','content':'查进度'}],'tool_context':{'claim_id':str(claim.pk)}},format='json').status_code==404


@pytest.mark.mysql
@pytest.mark.django_db(transaction=True)
def test_bad_planner_format_falls_back_to_natural_model_reply(assistant_domain):
 from apps.assistant.providers import ProviderProtocolError
 client=authenticated_client(assistant_domain)
 with patch('apps.assistant.views.converse',side_effect=ProviderProtocolError()),patch('apps.assistant.conversation.natural_reply',return_value='先别着急，我们先聊聊你最后一次使用它的情况。') as natural:
  result=client.post('/api/v1/assistant/conversation/',{'messages':[{'role':'user','content':'我丢了黑色耳机，现在有点着急'}]},format='json')
 assert result.status_code==200
 assert result.data['data']['reply']=='先别着急，我们先聊聊你最后一次使用它的情况。'
 natural.assert_called_once()


def test_unknown_location_also_blocks_rephrased_building_questions():
 result=guard_question({'intent':'ask','reply':'那是在哪个校区或者哪个楼栋附近丢的吗？','question_field':'none'},['location'])
 assert result['intent']=='search'
 assert '哪个楼栋' not in result['reply']
