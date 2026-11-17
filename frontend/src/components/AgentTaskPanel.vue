<script setup lang="ts">
import ListPager from './ListPager.vue'
import {useListPage} from '../composables/useListPage'
import {apiCollection} from '../api/collections'
import { computed, defineAsyncComponent, nextTick, reactive, ref, watch } from 'vue'
import { api, readableApiError } from '../api/client'

type Candidate = { id:string;title:string;description:string;image_url?:string;image_note?:string;category_id:number;location:string;color:string;brand:string }
type CoordinateCandidate={latitude:number;longitude:number;label?:string;coordinate_system?:'GCJ02'}
type Publication = {occurred_date?:string;location_candidate_ids?:number[];location_candidate_points?:CoordinateCandidate[]; kind:string;title:string;description:string;category:number|string;location:number|string;occurred_at:string;brand:string;color:string }
type Owned = { id:string;title:string;category_id:number }
export type AgentTask = { context_token?:string;ui_action?:{type:string;index?:number};excluded_id?:string;stage:string;description:string;reply:string;candidates?:Candidate[];publication?:Publication;options?:{categories:{id:number;name:string}[];locations:{id:number;name:string}[];candidate_locations?:{id:number;name:string}[]};owned_lost?:Owned[];tool_trace?:{tool:string;status:string}[] }
type Claim = { viewer_role?:string;statement?:string;id:string;status:string;item_title:string;allowed_actions:string[];conversation_id?:string|null;custody_station?:{name?:string;address?:string};decision_note?:string;appointment?:{verified_at?:string|null;claimant_confirmed_at?:string|null}|null }
const props = withDefaults(defineProps<{ task:AgentTask;photos?:{key:string;file:File;url:string}[] }>(),{photos:()=>[]})
const emit = defineEmits<{ exclude:[id:string]; progress:[text:string];published:[] }>()
const selected = ref<Candidate|null>(null), publishing = ref(false), busy = ref(false), error = ref(''), notice = ref('')
const eventDate=ref(''), eventTime=ref('')
const publicationPanel=ref<HTMLFormElement>()
const showLocationMap=ref(false)
const AMapCampus=defineAsyncComponent(()=>import('./AMapCampus.vue'))
const publication = reactive<Publication>({kind:'LOST',title:'',description:'',category:'',location:'',occurred_at:'',brand:'',color:''})
watch(()=>[publication.occurred_at,publication.occurred_date],()=>{eventDate.value=publication.occurred_at?.slice(0,10)||publication.occurred_date||'';eventTime.value=publication.occurred_at?.slice(11,16)||''})
const owned = ref<Owned[]>([]), related = ref(''), statement = ref(''), claim = ref<Claim|null>(null)
const counterpartMessage = ref(''), thread = ref<{id:number;body:string;sender_name?:string}[]>([])
const appointment = reactive({station:'',date:''}), stations = ref<{id:number;name:string}[]>([]), code = ref('')
const enteredCode=ref('')
const priorClaims=ref<Claim[]>([])
const reviewDecision=ref('NEEDS_INFO'),reviewNote=ref('')
async function reviewClaim(){void perform(async()=>{if(!claim.value||!reviewNote.value.trim())return;claim.value={...claim.value,...(await action('decide',{claim_id:claim.value.id,decision:reviewDecision.value,note:reviewNote.value.trim()})).claim};notice.value='已记录你的核验决定';emit('progress',notice.value)})}
const publishedItemId=ref('')
const actionKeys = new Map<string,string>()
function handleIntent(text:string):{reply:string}|null {
  if(busy.value)return {reply:'这一步还在办理，我会显示实际结果，请稍等。'}
  if(/都不是|都不对|没有我的/.test(text)&&props.task.candidates?.length){for(const row of [...props.task.candidates])emit('exclude',row.id);selected.value=null;if(/发布|寻物启事|招领信息/.test(text)&&props.task.publication){openPublication();return {reply:'好，这几条先排除。我把发布内容整理好了，你核对后再提交。'}}return {reply:'好，这几条先排除。你还记得其他外观特征吗？也可以让我准备一条寻物启事。'}}
  if(/不要发布|不想发布|暂不发布|先不发布|先别发布/.test(text)){publishing.value=false;return {reply:'好，先不发布。我们可以继续找线索，或者聊聊你最后一次使用它的情况。'}}
  if(/^(?:确认发布|确认提交发布|就这样发布)[。！! ]*$/.test(text)&&publishing.value){publish();return {reply:'我会提交你刚核对的发布内容，实际结果会显示在这里。'}}
  const number=text.match(/第([一二三四五12345])(?:个|条|件)/)
  if(number && props.task.candidates?.length){const n='一二三四五'.indexOf(number[1]!);const row=props.task.candidates[n>=0?n:Number(number[1])-1];if(row){if(/不是|排除|不对/.test(text)){emit('exclude',row.id);return {reply:'已排除这条线索，其他候选还保留着。'}}choose(row);return {reply:`我已展开“${row.title}”，请核对实物细节。`}}}
  if(/不是我的|不是这[个件条]/.test(text)&&selected.value){emit('exclude',selected.value.id);selected.value=null;return {reply:'已排除这件物品，请继续看其他线索。'}}
  if(/招领/.test(text)&&props.task.publication?.kind!=='FOUND')return null
  if(/(?:帮我|确认|请)?(?:发布|登记)(?:寻物|遗失|招领|信息)/.test(text)&&props.task.publication){openPublication();return {reply:'我已经准备好发布信息。类别、地点和时间需要你最后核对，确认后我直接提交。'}}
  if(claim.value?.allowed_actions.includes('decide')&&/^核验说明[:：]/.test(text)){reviewNote.value=text.replace(/^核验说明[:：]/,'').trim();return {reply:'核验说明已记录，请选择通过、驳回或要求补充，再确认提交。'}}
  if(claim.value?.allowed_actions.includes('decide')&&/^(?:通过|驳回)(?:这条)?认领|^要求补充(?:材料)?/.test(text)){reviewDecision.value=/^通过/.test(text)?'APPROVE':/^驳回/.test(text)?'REJECT':'NEEDS_INFO';return {reply:'我已准备这项核验决定。请填写核验说明，核对后说“确认提交核验决定”。'}}
  if(claim.value?.allowed_actions.includes('decide')&&/^确认提交核验决定[。！! ]*$/.test(text)){if(!reviewNote.value.trim())return {reply:'请先填写核验说明，说明核对结果或还需补充什么。'};reviewClaim();return {reply:'正在提交你确认的核验决定，结果会显示在这里。'}}
  if(/^(?:私密|核验|独有)(?:核验)?特征[:：]/.test(text)){
    if(!selected.value && claim.value?.status!=='NEEDS_INFO')return {reply:'这属于私密核验信息，我不会把它放进公开描述。请先选中候选物品，或打开需要补充材料的认领记录。'}
    statement.value=text.replace(/^[^:：]+[:：]/,'').trim();return {reply:'私密核验特征已单独记录，不会进入公开描述。确认后我可以提交核验。'}
  }
  if(/^(?:确认提交认领|确认提交认领申请)[。！! ]*$/.test(text)&&selected.value){submitClaim();return {reply:'我会按你的确认提交申请，办理结果会显示在下方。'}}
  if(/(?:查看|查|刷新).*(?:进度|状态|消息)/.test(text)&&claim.value){refresh();return {reply:'正在读取实际核验进度和消息。'}}
  if(/^(?:确认选择双方直接交接|确认选择直接交接|确认直接交接)[。！! ]*$/.test(text)&&claim.value?.allowed_actions.includes('start_direct_handover')){handover('start_handover');return {reply:'正在办理双方直接交接。'}}
  if(/^(?:我已拿到实物，确认我的交接|我已收到物品，确认我的交接|实物已交给对方，确认我的交接)[。！! ]*$/.test(text)&&claim.value?.allowed_actions.includes('confirm_direct_handover')){handover('confirm_handover');return {reply:'正在记录你这一方的实物交接确认，完成状态以双方确认为准。'}}
  return null
}
function applyAssistantAction(action?:{type:string;index?:number}){
 if(action?.type==='publish'&&props.task.publication)openPublication()
 else if(action?.type==='select'&&action.index){const row=props.task.candidates?.[action.index-1];if(row)choose(row)}
 else if(action?.type==='continue_claim'){if(claim.value)refresh();else loadClaims()}
}
function getToolContext(){return {...(claim.value?{claim_id:claim.value.id}:{}),...(publishedItemId.value?{published_item_id:publishedItemId.value}:{}),...(selected.value?{selected_item_id:selected.value.id}:{})}}
function resetSession(){selected.value=null;publishing.value=false;claim.value=null;publishedItemId.value='';priorClaims.value=[];notice.value='';error.value='';statement.value='';thread.value=[]}
defineExpose({handleIntent,applyAssistantAction,getToolContext,resetSession})
function loadClaims(){void perform(async()=>{priorClaims.value=(await apiCollection<{data:{items:(Claim&{viewer_role:string})[]}}>('/claims/?page_size=100')).data.items;if(!priorClaims.value.length)notice.value='你目前没有待办，可以告诉我丢失或拾到了什么。'})}
function resume(item:Claim){reviewNote.value='';reviewDecision.value='NEEDS_INFO';claim.value=item;notice.value='已接上这条认领记录，可以继续办理。';refresh()}
const compatible = computed(() => owned.value.filter(item => item.category_id === selected.value?.category_id))
const labels:Record<string,string> = {SUBMITTED:'等待对方核验',NEEDS_INFO:'需要补充证明',APPROVED:'认领已通过',HANDOVER_PENDING:'等待实物交接',COMPLETED:'已完成找回',REJECTED:'认领未通过',CANCELLED:'已取消'}
let lastAssistantPublication:Partial<Publication>={}
watch(() => props.task, task => {
  if(selected.value&&!task.candidates?.some(row=>row.id===selected.value?.id))selected.value=null
  if (task.publication) {
    Object.assign(publication,Object.fromEntries(Object.entries(task.publication).filter(([key,value])=>!publishing.value||JSON.stringify(value)!==JSON.stringify(lastAssistantPublication[key as keyof Publication]))))
    lastAssistantPublication=JSON.parse(JSON.stringify(task.publication))
  }
  if(publication.occurred_at && /Z|[+]\d\d:\d\d$/.test(publication.occurred_at)) {
    const d=new Date(publication.occurred_at);publication.occurred_at=new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)
  }
  owned.value = task.owned_lost ?? owned.value
}, {immediate:true})
function choose(candidate:Candidate) {
  selected.value = candidate; related.value = owned.value.find(i => i.category_id === candidate.category_id)?.id ?? ''; error.value = ''; notice.value = ''
}
function openPublication() {
  Object.assign(publication,{location_candidate_ids:[],location_candidate_points:[]},props.task.publication)
  showLocationMap.value=false
  if (selected.value) publication.category = selected.value.category_id
  if(publication.occurred_at && /Z|[+]\d\d:\d\d$/.test(publication.occurred_at)){const d=new Date(publication.occurred_at);publication.occurred_at=new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)}
  publishing.value = true; error.value = ''
  void nextTick(()=>publicationPanel.value?.scrollIntoView?.({block:'start',behavior:'smooth'}))
}
const locationCount=computed(()=>(publication.location_candidate_ids?.length??0)+(publication.location_candidate_points?.length??0))
const locationLimit=computed(()=>publication.kind==='LOST'?5:1)
const selectedLocations=computed(()=>(publication.location_candidate_ids??[]).map(id=>props.task.options?.candidate_locations?.find(row=>row.id===id)).filter((row):row is {id:number;name:string}=>!!row))
function chooseLocation(row:{id:number}){
 if(!props.task.options?.candidate_locations?.some(entry=>entry.id===row.id))return
 const ids=publication.location_candidate_ids??[]
 if(ids.includes(row.id)){publication.location_candidate_ids=ids.filter(id=>id!==row.id);return}
 if(publication.kind==='FOUND'){publication.location_candidate_ids=[row.id];publication.location_candidate_points=[];error.value='';return}
 if(ids.length>=locationLimit.value){error.value='最多选择5个可能地点，可以移除或调整顺序。';return}
 publication.location_candidate_points=[];publication.location_candidate_ids=[...ids,row.id];error.value=''
}
function pickLocationPoint(point:CoordinateCandidate){
 const rows=publication.location_candidate_points??[]
 if(rows.some(row=>Math.abs(row.latitude-point.latitude)<.000001&&Math.abs(row.longitude-point.longitude)<.000001))return
 if(publication.kind==='FOUND')publication.location_candidate_points=[{...point,coordinate_system:'GCJ02'}]
 else if(rows.length<locationLimit.value)publication.location_candidate_points=[...rows,{...point,coordinate_system:'GCJ02'}]
 else {error.value='最多选择5个可能地点。';return}
 publication.location_candidate_ids=[];error.value=''
}
function moveLocation(kind:'ids'|'points',index:number,direction:-1|1){
 const rows=kind==='ids'?[...(publication.location_candidate_ids??[])]:[...(publication.location_candidate_points??[])]
 const target=index+direction;if(target<0||target>=rows.length)return
 ;[rows[index],rows[target]]=[rows[target]!,rows[index]!]
 if(kind==='ids')publication.location_candidate_ids=rows as number[]
 else publication.location_candidate_points=rows as CoordinateCandidate[]
}
watch(()=>publication.kind,kind=>{if(kind==='FOUND'){publication.location_candidate_ids=publication.location_candidate_ids?.slice(0,1);publication.location_candidate_points=publication.location_candidate_points?.slice(0,1)}})
async function action(name:string,payload:Record<string,unknown>,confirmed=true) {
  const signature = JSON.stringify([name,payload,name==='publish'?props.photos.map(row=>row.key):[]])
  if (!actionKeys.has(signature)) actionKeys.set(signature,crypto.randomUUID())
  if(name==='publish'&&props.photos.length){
    const form=new FormData();form.set('action',name);form.set('payload',JSON.stringify(payload));form.set('confirmed',String(confirmed));form.set('key',actionKeys.get(signature)!);for(const row of props.photos)form.append('photos',row.file,row.file.name)
    return (await api<{data:{item?:Owned&{review_status:string};claim?:Claim;message?:string;one_time_code?:string}}>('/assistant/agent/actions/',{method:'POST',body:form})).data
  }
  return (await api<{data:{item?:Owned&{review_status:string};claim?:Claim;message?:string;one_time_code?:string}}>('/assistant/agent/actions/', {
    method:'POST',body:JSON.stringify({action:name,payload,confirmed,key:actionKeys.get(signature)})})).data
}
async function perform(work:()=>Promise<void>) {
  if (busy.value) return
  busy.value=true;error.value=''
  try { await work() } catch(reason) { error.value=readableApiError(reason,'这一步暂未完成，请重试。') } finally { busy.value=false }
}
function publish() { void perform(async()=>{
  if (!publication.category || !publication.location || !(publication.occurred_at||(eventDate.value&&eventTime.value))) { error.value='发布前还需要确认物品类别、公开范围和时间；不确定时可以先不发布，继续查找。';return }
  const date = new Date(eventDate.value&&eventTime.value?`${eventDate.value}T${eventTime.value}`:publication.occurred_at)
  if (Number.isNaN(date.getTime())) { error.value='请确认有效的事件时间。';return }
  const {occurred_date: _dateHint,...payload}=publication
  const result = await action('publish',{...payload,category:Number(publication.category),location:Number(publication.location),occurred_at:date.toISOString()})
  if (result.item) {
    publishedItemId.value=result.item.id;emit('published')
    notice.value = result.item.review_status === 'APPROVED' ? '已帮你发布成功。' : '已经提交，等待内容审核；不会跳过审核。'
    if (result.item.review_status === 'APPROVED' && publication.kind === 'LOST') {
      owned.value=[...owned.value,result.item]; related.value=result.item.id
    }
    publishing.value=false; emit('progress',notice.value)
  }
}) }
function submitClaim() { void perform(async()=>{
  if (!selected.value || !related.value || !statement.value.trim()) { error.value='还需要关联遗失线索，并告诉我只有失主知道的核验特征。';return }
  const result = await action('claim',{found_item_id:selected.value.id,related_lost_item_id:related.value,statement:statement.value.trim()})
  claim.value=result.claim??null;statement.value='';notice.value=result.message??'已提交认领';emit('progress',notice.value)
}) }
function supplement(){void perform(async()=>{if(!claim.value||!statement.value.trim())return;claim.value=(await action('supplement',{claim_id:claim.value.id,statement:statement.value.trim()})).claim??claim.value;statement.value='';notice.value='补充材料已提交，等待再次核验。'})}
function refresh() { void perform(async()=>{
  if (!claim.value) return
  claim.value=(await action('status',{claim_id:claim.value.id},false)).claim??claim.value
  if(claim.value.allowed_actions.includes('decide'))claim.value=(await api<{data:Claim}>(`/claims/${claim.value.id}/`)).data
  notice.value=labels[claim.value.status]??claim.value.status
  if (claim.value.conversation_id) {
    const result=await api<{data:{messages:{id:number;body:string;sender_name?:string}[]}}>(`/messages/${claim.value.conversation_id}/`)
    thread.value=result.data.messages??[]
  }
}) }
function handover(name:string) { void perform(async()=>{
  if (!claim.value) return
  const result=await action(name,{claim_id:claim.value.id})
  claim.value=result.claim??claim.value
  notice.value=claim.value.status==='COMPLETED'?'交接已确认，找回流程完成。':'已记录你的操作，等待对方完成应有步骤。'
}) }
function sendMessage() { void perform(async()=>{
  if (!claim.value?.conversation_id || !counterpartMessage.value.trim()) return
  await api(`/messages/${claim.value.conversation_id}/messages/`,{method:'POST',body:JSON.stringify({body:counterpartMessage.value.trim()})})
  counterpartMessage.value='';notice.value='消息已发送给对方。'
}) }
function loadStations() { void perform(async()=>{
  stations.value=(await api<{data:{items:{id:number;name:string}[]}}>('/stations/')).data.items
}) }
function schedule() { void perform(async()=>{
  if (!claim.value || !appointment.station || !appointment.date) { error.value='请选择服务站和时间。';return }
  const result=await action('schedule',{claim_id:claim.value.id,station_id:Number(appointment.station),scheduled_at:new Date(appointment.date).toISOString()})
  claim.value=result.claim??claim.value;code.value=result.one_time_code??'';notice.value='预约已完成，请妥善保管交接码。'
}) }
function verifyStationCode(){void perform(async()=>{
  if(!claim.value || !enteredCode.value.trim())return
  // Use the existing non-atomic verification endpoint: failed-attempt counters
  // must commit even when verification raises a validation error.
  const result=await api<{data:{verified_at?:string|null;claimant_confirmed_at?:string|null}}>(`/claims/${claim.value.id}/handover/verify/`,{method:'POST',body:JSON.stringify({code:enteredCode.value.trim()})})
  claim.value.appointment=result.data;enteredCode.value='';notice.value='交接码已核验；实物拿到后再确认你这一方的交接。'
})}
const {page:priorClaimPage,rows:pagedPriorClaims}=useListPage(priorClaims)
</script>

<template>
  <section class="agent-task-panel" aria-label="小寻执行结果">
    <template v-if="!claim"><button class="agent-secondary-action" type="button" :disabled="busy" @click="loadClaims">继续已有认领</button><button class="agent-secondary-action" type="button" :disabled="busy" @click="loadClaims">处理收到的认领</button><div v-if="priorClaims.length"><button v-for="item in pagedPriorClaims" :key="item.id" type="button" @click="resume(item)">{{item.item_title}} · {{labels[item.status]??item.status}}</button><ListPager :page="priorClaimPage" :total="priorClaims.length" @change="priorClaimPage=$event"/></div></template>
    <div class="agent-tool-status" v-if="task.tool_trace?.length"><span>✓ 已整理物品特征</span><span v-if="task.stage==='results'">✓ 已检索真实线索</span></div>
    <template v-if="!claim">
      <div v-if="!selected && task.candidates?.length" class="agent-candidate-list">
        <article v-for="candidate in task.candidates" :key="candidate.id" class="agent-candidate">
          <img v-if="candidate.image_url" :src="candidate.image_url" :alt="candidate.title"/><div><strong>{{candidate.title}}</strong><p>{{candidate.location}} · {{candidate.color}}</p><p>{{candidate.description}}</p><small v-if="candidate.image_note">{{candidate.image_note}}</small><div class="agent-card-actions"><button type="button" :disabled="busy" @click="choose(candidate)">查看并核对这件物品</button><button type="button" :disabled="busy" @click="emit('exclude',candidate.id)">不是我的</button></div></div>
        </article>
      </div>
      <section v-if="selected" class="agent-selected"><div class="agent-card-top"><strong>正在核对：{{selected.title}}</strong><button type="button" @click="selected=null">返回候选</button></div><img v-if="selected.image_url" :src="selected.image_url" :alt="selected.title"/><p>{{selected.description}}</p><p>{{selected.location}} · {{selected.brand}} {{selected.color}}</p>
        <template v-if="task.publication?.kind==='LOST'">
          <label v-if="compatible.length">关联你的遗失信息<select v-model="related"><option v-for="item in compatible" :key="item.id" :value="item.id">{{item.title}}</option></select></label>
          <p v-else>认领需要一条你自己的同类别遗失信息。我可以在这里帮你登记，再继续办理。</p>
          <button v-if="!compatible.length" type="button" @click="openPublication">帮我登记遗失信息</button>
          <template v-if="compatible.length"><label>私密核验特征<textarea v-model="statement" maxlength="1500" placeholder="只有你知道、公开图片里看不到的细节；不会写入公开寻物描述。"/></label><button type="button" :disabled="busy || !statement.trim()" @click="submitClaim">确认是我的，提交认领申请</button></template>
        </template>
      </section>
      <button v-if="!publishing && task.publication" class="agent-secondary-action" type="button" :disabled="busy" @click="openPublication">{{task.publication.kind==='LOST'?'帮我发布寻物信息':'帮我发布招领信息'}}</button>
      <form v-if="publishing" ref="publicationPanel" class="agent-publication" @submit.prevent="publish"><strong>核对发布内容</strong><label>信息类型<select v-model="publication.kind" aria-label="信息类型"><option value="LOST">寻物启事</option><option value="FOUND">失物招领</option></select></label><label>标题<input v-model="publication.title" maxlength="120" required/></label><label>物品描述<textarea v-model="publication.description" maxlength="3000" required rows="4"/></label><label>类别<select v-model="publication.category" required><option value="">请选择物品类别</option><option v-for="entry in task.options?.categories" :key="entry.id" :value="entry.id">{{entry.name}}</option></select></label><label>公开地点<select v-model="publication.location" required><option value="">请选择公开范围</option><option v-for="entry in task.options?.locations" :key="entry.id" :value="entry.id">{{entry.name}}</option></select></label><section class="agent-location-picker" aria-label="可能地点选择"><strong>{{publication.kind==='LOST'?'可能遗失地点（最多5个）':'拾获地点（1个）'}}</strong><div class="location-choices"><button v-for="row in task.options?.candidate_locations??[]" :key="row.id" type="button" :aria-pressed="publication.location_candidate_ids?.includes(row.id)??false" @click="chooseLocation(row)">{{row.name}}</button></div><button type="button" @click="showLocationMap=!showLocationMap">{{showLocationMap?'收起地图':'在地图上选择地点'}}</button><AMapCampus v-if="showLocationMap" compact pickable :selected-protected-location-ids="publication.location_candidate_ids??[]" :selected-coordinate-points="publication.location_candidate_points??[]" @select-protected-location="chooseLocation" @pick="pickLocationPoint"/><ol class="location-ranking"><li v-for="(row,index) in selectedLocations" :key="row.id"><span>{{row.name}}</span><button type="button" :disabled="index===0" aria-label="提高地点可能性排名" @click="moveLocation('ids',index,-1)">↑</button><button type="button" :disabled="index===selectedLocations.length-1" aria-label="降低地点可能性排名" @click="moveLocation('ids',index,1)">↓</button><button type="button" @click="chooseLocation(row)">移除</button></li><li v-for="(row,index) in publication.location_candidate_points??[]" :key="index"><span>{{row.label||'地图选点'}}</span><button type="button" :disabled="index===0" aria-label="提高地图点可能性排名" @click="moveLocation('points',index,-1)">↑</button><button type="button" :disabled="index===(publication.location_candidate_points?.length??0)-1" aria-label="降低地图点可能性排名" @click="moveLocation('points',index,1)">↓</button><button type="button" @click="publication.location_candidate_points?.splice(index,1)">移除</button></li></ol><span v-if="locationCount" class="location-count">已选 {{locationCount}} / {{locationLimit}}</span></section><label>事件日期<input v-model="eventDate" type="date" required aria-label="事件日期"/></label><label>具体时间<input v-model="eventTime" type="time" required aria-label="具体时间"/></label><div class="agent-card-actions"><button type="button" @click="publishing=false">暂不提交</button><button type="submit" :disabled="busy">确认以上信息，提交发布</button></div></form>
    </template>
    <section v-if="claim" class="agent-claim-progress"><button type="button" :disabled="busy" @click="claim=null;loadClaims()">返回认领待办</button><strong>{{claim.viewer_role&&claim.viewer_role!=='CLAIMANT'?'收到的申请 · ':''}}{{labels[claim.status]??claim.status}}</strong><p>{{claim.item_title}}</p><p v-if="claim.decision_note">核验意见：{{claim.decision_note}}</p><p v-if="['SUBMITTED','NEEDS_INFO'].includes(claim.status)">{{claim.viewer_role==='CLAIMANT'||!claim.viewer_role?'申请已提交，等待拾得者或服务站核验。':'请核对申请材料后作出决定。'}}</p><p v-if="claim.custody_station?.name">保管服务站：{{claim.custody_station.name}} {{claim.custody_station.address}}</p><button type="button" :disabled="busy" @click="refresh">查看最新进度和消息</button>
      <form v-if="claim.status==='NEEDS_INFO'&&claim.viewer_role!=='FINDER'&&claim.viewer_role!=='STAFF'&&claim.viewer_role!=='ADMIN'" @submit.prevent="supplement"><label>补充私密核验特征<textarea v-model="statement" maxlength="1500" required/></label><button :disabled="busy || !statement.trim()">确认补充并提交核验</button></form>
      <button v-if="['REJECTED','CANCELLED'].includes(claim.status)" type="button" @click="claim=null;selected=null">继续找其他线索</button>
      <form v-if="claim.allowed_actions.includes('decide')" @submit.prevent="reviewClaim"><strong>核验认领材料</strong><p>{{claim.statement}}</p><label>核验决定<select v-model="reviewDecision" aria-label="核验决定"><option value="NEEDS_INFO">要求补充材料</option><option value="APPROVE">通过认领</option><option value="REJECT">驳回认领</option></select></label><label>核验说明<textarea v-model="reviewNote" required minlength="2" maxlength="1000"/></label><button :disabled="busy||!reviewNote.trim()">确认提交核验决定</button></form><button v-if="claim.allowed_actions.includes('complete_station_pickup')" type="button" :disabled="busy" @click="handover('complete_station_pickup')">实物已交给申请人，确认服务站交接</button><button v-if="claim.allowed_actions.includes('start_direct_handover')" type="button" :disabled="busy" @click="handover('start_handover')">确认选择双方直接交接</button>
      <button v-if="claim.allowed_actions.includes('confirm_direct_handover')" type="button" :disabled="busy" @click="handover('confirm_handover')">{{claim.viewer_role==='CLAIMANT'||!claim.viewer_role?'我已拿到实物，确认我的交接':'实物已交给对方，确认我的交接'}}</button>
      <template v-if="claim.allowed_actions.includes('schedule_handover')"><button type="button" @click="loadStations">帮我预约服务站</button><form v-if="stations.length" @submit.prevent="schedule"><select v-model="appointment.station" aria-label="预约服务站" required><option v-for="station in stations" :key="station.id" :value="station.id">{{station.name}}</option></select><input v-model="appointment.date" type="datetime-local" aria-label="预约时间" required/><button :disabled="busy">确认预约</button></form></template>
      <p v-if="code">本次交接码：<strong>{{code}}</strong>。请妥善保管，不要发给无关人员。</p>
      <template v-if="claim.status==='HANDOVER_PENDING' && claim.appointment"><form v-if="!claim.appointment.verified_at" @submit.prevent="verifyStationCode"><label>服务站交接码<input v-model="enteredCode" inputmode="numeric" maxlength="6" required/></label><button :disabled="busy">核验交接码</button></form><button v-else-if="!claim.appointment.claimant_confirmed_at" type="button" :disabled="busy" @click="handover('confirm_station_handover')">已拿到实物，确认我的服务站交接</button></template>
      <template v-if="claim.conversation_id"><div class="agent-counterpart-messages"><p v-for="message in thread" :key="message.id">{{message.sender_name}}：{{message.body}}</p></div><form @submit.prevent="sendMessage"><label>给拾得者或协调员留言<textarea v-model="counterpartMessage" maxlength="2000"/></label><button :disabled="busy || !counterpartMessage.trim()">确认发送给对方</button></form></template>
    </section>
    <p v-if="notice" class="agent-action-notice" role="status">{{notice}}</p><p v-if="error" class="agent-action-error" role="alert">{{error}}</p><p v-if="busy" role="status">正在办理这一步…</p>
  </section>
</template>

<style scoped>
.agent-task-panel{margin-top:10px;font-size:13px;line-height:1.7;color:#355270}.agent-tool-status{display:flex;flex-wrap:wrap;gap:8px;color:#218674;font-size:11px;margin-bottom:12px}.agent-candidate-list{display:grid;gap:10px}.agent-candidate,.agent-selected,.agent-publication,.agent-claim-progress{border:1px solid #d8e6f7;border-radius:15px;padding:13px;background:#fff;margin-bottom:12px;overflow-wrap:anywhere}.agent-candidate{display:grid;grid-template-columns:72px 1fr;gap:11px}.agent-candidate:not(:has(img)){grid-template-columns:1fr}.agent-candidate img{width:72px;height:78px;object-fit:cover;border-radius:10px}.agent-candidate strong{color:#1d3b60}.agent-candidate p{font-size:12px;line-height:1.7;margin:5px 0}.agent-candidate small{font-size:10px;color:#8192a5}.agent-task-panel button{border:1px solid #d6e3f6;background:#f2f7ff;color:#2467c6;font-size:12px;padding:7px 10px;border-radius:9px;cursor:pointer;margin:4px 4px 4px 0}.agent-task-panel button:disabled{opacity:.5;cursor:default}.agent-card-actions,.agent-card-top{display:flex;justify-content:space-between;gap:6px;flex-wrap:wrap}.agent-selected>img{width:100%;max-height:190px;object-fit:contain;border-radius:12px;margin-top:10px}.agent-task-panel label{display:grid;gap:6px;margin:10px 0;font-size:12px}.agent-task-panel select,.agent-task-panel input,.agent-task-panel textarea{max-width:100%;width:100%;box-sizing:border-box;border:1px solid #d3e1f3;background:#fbfdff;border-radius:9px;padding:9px;color:#294566;font:inherit;font-size:12px}.agent-task-panel textarea{min-height:70px;resize:vertical}.agent-action-notice{padding:9px 12px;border-radius:10px;color:#168568;background:#edfaf5}.agent-action-error{color:#ac4f43}.agent-counterpart-messages{max-height:150px;overflow:auto;background:#f5f8fc;padding:10px;border-radius:10px}.agent-publication>p{white-space:pre-wrap}.agent-location-picker{margin:14px 0}.location-choices{display:flex;gap:4px;flex-wrap:wrap;margin-top:8px}.location-choices button[aria-pressed=true]{background:#246ae4;color:white}.location-ranking{padding-left:22px}.location-ranking li{margin:6px 0}.location-ranking li>span{margin-right:7px}.location-count{color:#54769a}
</style>
