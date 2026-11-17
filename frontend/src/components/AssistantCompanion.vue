<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import XunAgent from './XunAgent.vue'
import AgentTaskPanel, { type AgentTask } from './AgentTaskPanel.vue'
import { api, readableApiError } from '../api/client'
import { useAuthStore } from '../stores/auth'
import { xunSpokenText } from '../utils/xunVoice'

type Turn = { role: 'user' | 'assistant'; content: string; tool?:boolean }
const props = defineProps<{ mode: 'text' | 'image'; description: string; kind?: 'LOST' | 'FOUND';initialPhoto?:File|null }>()
const emit = defineEmits<{ apply: [description: string]; continue: [] }>()
const auth = useAuthStore()
const open = ref(false), busy = ref(false), speaking = ref(false), bubble = ref(false)
const gesture = ref<'idle'|'wave'|'spin'|'wink'>('idle'), stage = ref<HTMLElement>()
let stageVisible = true, observer: IntersectionObserver | undefined
const input = ref(''), error = ref(''), draft = ref(''), applied = ref(false), pending = ref('')
const turns = ref<Turn[]>([]), panel = ref<HTMLElement>(), entry = ref<HTMLTextAreaElement>(), messages = ref<HTMLElement>()
const inheritWorkbench=ref(true)
const task = ref<AgentTask|null>(null), excluded = ref<string[]>([])
const emptyTask:AgentTask={stage:'collecting',description:'',reply:''}
const taskPanel = ref<InstanceType<typeof AgentTaskPanel>>()
const photoInput = ref<HTMLInputElement>(), photoObservation = ref('')
const attachedPhotos=ref<{key:string;file:File;url:string}[]>([])
function removePhoto(key:string){const row=attachedPhotos.value.find(row=>row.key===key);if(row)URL.revokeObjectURL(row.url);attachedPhotos.value=attachedPhotos.value.filter(row=>row.key!==key)}
function clearPhotos(){for(const row of attachedPhotos.value)URL.revokeObjectURL(row.url);attachedPhotos.value=[]}
const greeting = '我是小寻。告诉我丢了什么，我来整理、找线索，再陪你核对和办理认领。整个过程都可以在这里完成。'
const bubbles = ['记不清细节？和我聊聊，我帮你理一理。', '挂件、贴纸和划痕，都是很有用的线索。', '点点我，把你记得的情况告诉我。']
const bubbleIndex = ref(0)
const voiceEnabled=ref(false), voiceLoading=ref(false)
let audio:HTMLAudioElement|null=null, audioUrl='', voiceController:AbortController|null=null, voiceVersion=0
let voiceJobKey='',voiceRelease:Promise<void>=Promise.resolve()
async function releaseSpeech(key:string){try{let result=await api<{data:{workflow_id?:string;status?:string}}>(`/assistant/jobs/?action=${encodeURIComponent('/api/v1/assistant/speech/')}`,{headers:{'Idempotency-Key':key}});if(!result.data.workflow_id||result.data.status!=='RUNNING')return;const path=`/assistant/jobs/${result.data.workflow_id}/`;await api(path,{method:'POST',body:'{}'});const deadline=Date.now()+85_000;while(Date.now()<deadline){const state=await api<{data:{status:string}}>(path);if(state.data.status!=='RUNNING')return;await new Promise(resolve=>setTimeout(resolve,500))}}catch{/* A speech request rejected before admission has no running job. */}}
let controller: AbortController | null = null, requestKey = '', timeout: ReturnType<typeof setTimeout> | undefined
let idleTimer: ReturnType<typeof setInterval> | undefined, hideTimer: ReturnType<typeof setTimeout> | undefined
let gestureTimer: ReturnType<typeof setInterval> | undefined, poseTimer: ReturnType<typeof setTimeout> | undefined
let generation = 0, previousFocus: HTMLElement | null = null
let runningAction = '/api/v1/assistant/conversation/'
function stopSpeech() {
  if(voiceLoading.value&&voiceJobKey){const key=voiceJobKey;voiceJobKey='';voiceRelease=releaseSpeech(key)}
  voiceVersion++;voiceController?.abort();voiceController=null
  if(audio){audio.onended=null;audio.onerror=null;audio.pause();audio.removeAttribute('src');audio=null}
  if(audioUrl){URL.revokeObjectURL(audioUrl);audioUrl=''}
  speaking.value=false;voiceLoading.value=false
}
async function playSpeech(content:string) {
  stopSpeech()
  if(!voiceEnabled.value||!open.value||!auth.user)return
  const version=voiceVersion;voiceLoading.value=true;voiceController=new AbortController();voiceJobKey=crypto.randomUUID()
  const timer=setTimeout(()=>voiceController?.abort(),88_000)
  try{
    const result=await api<{data:{audio:string;mime:string}}>('/assistant/speech/',{method:'POST',
      body:JSON.stringify({text:xunSpokenText(content)}),signal:voiceController.signal,
      headers:{'Idempotency-Key':voiceJobKey}})
    if(version!==voiceVersion||!voiceEnabled.value||!open.value)return
    const bytes=Uint8Array.from(atob(result.data.audio),c=>c.charCodeAt(0))
    audioUrl=URL.createObjectURL(new Blob([bytes],{type:'audio/wav'}));audio=new Audio(audioUrl)
    audio.onended=()=>stopSpeech()
    audio.onerror=()=>{stopSpeech();error.value='声音播放失败，请再点一次试试。'}
    await audio.play();if(version===voiceVersion)speaking.value=true
  }catch(reason){if(version===voiceVersion){voiceEnabled.value=false;error.value=readableApiError(reason,'声音暂时没有准备好，请稍后再试。')}}
  finally{clearTimeout(timer);if(version===voiceVersion){voiceLoading.value=false;voiceController=null;voiceJobKey=''}}
}
function speak() {
  voiceEnabled.value=!voiceEnabled.value
  if(!voiceEnabled.value){stopSpeech();return}
  void playSpeech(turns.value.filter(t=>t.role==='assistant'&&!t.tool).at(-1)?.content || '嗨，我是小寻！别着急，咱们一起找。你丢了什么呀？')
}
async function show() {
  previousFocus = document.activeElement as HTMLElement
  open.value = true; bubble.value = false; gesture.value = 'idle'; clearTimeout(hideTimer); clearTimeout(poseTimer)
  await nextTick(); (auth.user ? entry.value : panel.value)?.focus()
  if(auth.user&&props.initialPhoto&&!turns.value.length&&!attachedPhotos.value.some(row=>row.file===props.initialPhoto))void readPhoto(props.initialPhoto)
}
defineExpose({show})
function close() { open.value = false; voiceEnabled.value=false; stopSpeech(); previousFocus?.focus() }
async function cancel() {
  const key = requestKey; requestKey = ''
  generation++; controller?.abort(); controller = null; busy.value = false; input.value ||= pending.value; pending.value = ''
  clearTimeout(timeout)
  if (!key) return
  try {
    const result = await api<{ data: { workflow_id: string } }>(`/assistant/jobs/?action=${encodeURIComponent(runningAction)}`, { headers: { 'Idempotency-Key': key } })
    await api(`/assistant/jobs/${result.data.workflow_id}/`, { method: 'POST', body: '{}' })
  } catch { /* Task may not yet exist; browser waiting has stopped. */ }
}
function reset() { clearPhotos(); inheritWorkbench.value=false; taskPanel.value?.resetSession(); void cancel(); stopSpeech(); turns.value = []; task.value = null; excluded.value = []; draft.value = ''; input.value = ''; error.value = ''; photoObservation.value=''; applied.value = false }
async function photo(event:Event) {const input=event.target as HTMLInputElement;const file=input.files?.[0];if(file)await readPhoto(file);input.value=''}
async function readPhoto(file:File) {
  if(busy.value)return
  stopSpeech()
  if(file.size>5*1024*1024){error.value='照片不能超过5MB。';return}
  if(attachedPhotos.value.length>=3){error.value='最多附加3张照片，请先移除一张。';return}
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)){error.value='请选择JPG、PNG或WebP照片。';return}
  attachedPhotos.value.push({key:crypto.randomUUID(),file,url:URL.createObjectURL(file)})
  busy.value=true;error.value='';controller=new AbortController();requestKey=crypto.randomUUID();runningAction='/api/v1/assistant/image/'
  const version=++generation,form=new FormData();form.append('image',file)
  timeout=setTimeout(()=>{void cancel();error.value='照片识别等待较久，请重试。'},80_000)
  try{await voiceRelease;if(version!==generation)return;const result=await api<{data:{observation:string}}>('/assistant/image/',{method:'POST',body:form,headers:{'Idempotency-Key':requestKey},signal:controller.signal});if(version===generation)photoObservation.value=result.data.observation}
  catch(reason){if(version===generation)error.value=readableApiError(reason,'照片暂未识别成功。')}
  finally{if(version===generation){clearTimeout(timeout);busy.value=false;controller=null;requestKey=''}}
}
function acceptPhoto(){input.value=(input.value+'\n图片外观（我已核对）：'+photoObservation.value).trim().slice(0,1200);photoObservation.value='';void send()}
function taskProgress(text:string){turns.value.push({role:'assistant',content:text,tool:true});void nextTick(()=>messages.value?.scrollTo?.({top:messages.value.scrollHeight,behavior:'smooth'}));if(voiceEnabled.value)void playSpeech(text)}
function exclude(id:string) { excluded.value.push(id); if(task.value?.candidates) task.value.candidates=task.value.candidates.filter(c=>c.id!==id) }
async function send() {
  const text = input.value.trim()
  if (!text || busy.value || !auth.user) return
  const handled=taskPanel.value?.handleIntent(text)
  if(handled){turns.value.push({role:'user',content:text,tool:true},{role:'assistant',content:handled.reply,tool:true});input.value='';void nextTick(()=>messages.value?.scrollTo?.({top:messages.value.scrollHeight,behavior:'smooth'}));if(voiceEnabled.value)void playSpeech(handled.reply);return}
  if (!task.value?.context_token && turns.value.filter(t=>!t.tool).length >= 14) { error.value = '这轮线索已经很多了，可以先办理当前结果，或开始新一轮。'; return }
  stopSpeech(); error.value = ''; applied.value = false
  const initial = !turns.value.length && inheritWorkbench.value && props.description.trim() ? `${props.description.trim()}\n${text}` : text
  if (initial.length > 1200) { error.value = '描述较长，请精简到1200字以内。'; return }
  const allHistory: Turn[] = [...turns.value.filter(t=>!t.tool).map(({role,content})=>({role,content})), { role: 'user', content: initial }]
  let history=task.value?.context_token?allHistory.slice(-15):allHistory
  while(task.value?.context_token && history.length>1 && history.reduce((total,turn)=>total+turn.content.length,0)>7600)history=history.slice(2)
  const visibleHistory=[...turns.value,{role:'user' as const,content:initial}]
  const version = ++generation, previousDescription = props.description
  pending.value = text; input.value = ''; busy.value = true
  controller = new AbortController(); requestKey = crypto.randomUUID()
  runningAction='/api/v1/assistant/conversation/'
  timeout = setTimeout(() => { void cancel(); error.value = '整理时间较长，请稍后重试；也可以直接填写描述。' }, 80_000)
  try {
    await voiceRelease
    if(version!==generation)return
    const result = await api<{ data: AgentTask }>('/assistant/conversation/', { method: 'POST',
      headers: { 'Idempotency-Key': requestKey }, signal: controller.signal,
      body: JSON.stringify({ kind: props.kind ?? 'LOST', messages: history, excluded_ids: excluded.value, context_token:task.value?.context_token??'', tool_context:taskPanel.value?.getToolContext()??{} }) })
    if (version !== generation) return
    turns.value = [...visibleHistory, { role: 'assistant', content: result.data.reply }]
    task.value = result.data
    if(result.data.excluded_id&&!excluded.value.includes(result.data.excluded_id))excluded.value.push(result.data.excluded_id)
    await nextTick();taskPanel.value?.applyAssistantAction(result.data.ui_action)
    draft.value = result.data.description
    // Preserve edits made while inference was in flight.
    if (draft.value && props.description === previousDescription) { emit('apply', draft.value); applied.value = true }
  } catch (reason) {
    if (version !== generation) return
    input.value = text; error.value = readableApiError(reason, '暂时无法联系小寻，请重试。')
  } finally {
    if (version === generation) { clearTimeout(timeout); busy.value = false; pending.value = ''; controller = null; requestKey = '' }
    await nextTick(); messages.value?.scrollTo?.({ top: messages.value.scrollHeight, behavior: 'smooth' })
    if(version===generation && !error.value && voiceEnabled.value && task.value)void playSpeech(task.value.reply)
  }
}
function apply() { emit('apply', draft.value); applied.value = true }
function continueSearch() { if (!applied.value) apply(); close(); emit('continue') }
function keys(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); close() }
  if (event.key !== 'Tab') return
  const nodes = panel.value?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], textarea:not(:disabled), select:not(:disabled), input:not(:disabled):not([hidden])')
  if (!nodes?.length) return
  const first = nodes[0]!, last = nodes[nodes.length - 1]!
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
watch(() => auth.user?.id, reset)
watch(() => props.kind, reset)
watch(open, value => { document.body.style.overflow = value ? 'hidden' : '' })
onMounted(() => {
  let lastMomentAt = -Infinity
  let lastBubbleAt = -Infinity
  let gestureIndex = 0
  const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false
  const pose = (index:number) => {
    lastMomentAt = Date.now()
    gestureIndex = index
    gesture.value = (['wave','wink','spin'] as const)[index]!
    clearTimeout(poseTimer)
    poseTimer = setTimeout(() => { gesture.value = 'idle' }, 7000)
  }
  const play = (index:number) => {
    lastBubbleAt = Date.now()
    bubbleIndex.value = index
    bubble.value = true
    clearTimeout(hideTimer)
    hideTimer = setTimeout(() => { bubble.value = false }, 7000)
  }
  let greeted = false
  if ('IntersectionObserver' in window && stage.value) {
    stageVisible = false
    observer = new IntersectionObserver(entries => {
      stageVisible = entries[0]?.isIntersecting ?? false
      if(stageVisible && !greeted && !open.value && !document.hidden && !reduced()){greeted=true;play(0);pose(0)}
      if(!stageVisible){bubble.value=false;gesture.value='idle';clearTimeout(hideTimer);clearTimeout(poseTimer)}
    },{threshold:.3})
    observer.observe(stage.value)
  } else if (!reduced()) { greeted=true;play(0);pose(0) }
  idleTimer = setInterval(() => {
    if (!stageVisible || busy.value || open.value || document.hidden || reduced() || Date.now()-lastBubbleAt < 55_000) return
    play((bubbleIndex.value + 1) % bubbles.length)
  }, 55_000)
  gestureTimer = setInterval(() => {
    if (!stageVisible || busy.value || open.value || document.hidden || reduced() || Date.now()-lastMomentAt < 20_000) return
    pose((gestureIndex+1)%3)
  }, 20_000)
})
onBeforeUnmount(() => { clearPhotos(); void cancel(); stopSpeech(); observer?.disconnect(); clearInterval(idleTimer); clearInterval(gestureTimer); clearTimeout(hideTimer); clearTimeout(poseTimer); document.body.style.overflow = '' })
</script>

<template>
  <section class="xun-companion" aria-label="小寻寻物助手">
    <div ref="stage" class="agent-stage">
      <Transition name="bubble"><div v-if="bubble && !open" class="agent-bubble">{{ bubbles[bubbleIndex] }}</div></Transition>
      <button class="agent-character" type="button" aria-label="和小寻聊聊" aria-haspopup="dialog" :aria-expanded="open" @click="show"><XunAgent :busy="busy" :speaking="speaking" :gesture="gesture" /></button>
    </div>
  </section>
  <Teleport to="body">
    <div v-if="open" class="xun-chat-backdrop" @click.self="close">
      <section ref="panel" class="xun-chat" role="dialog" aria-modal="true" aria-labelledby="xun-chat-title" tabindex="-1" @keydown="keys">
        <header class="xun-chat-header"><div class="chat-mini-agent"><XunAgent :busy="busy" :speaking="speaking" /></div><div><h2 id="xun-chat-title">和小寻一起找</h2><p>{{ busy ? '正在整理线索…' : '先聊清楚，再寻找' }}</p></div><button type="button" class="chat-close" aria-label="关闭聊天" @click="close">×</button></header>
        <div ref="messages" class="xun-chat-messages" role="log" aria-live="polite" aria-label="寻物对话">
          <p class="chat-turn assistant">{{ greeting }}</p><p v-for="(turn, index) in turns" :key="index" class="chat-turn" :class="turn.role">{{ turn.content }}</p><p v-if="pending" class="chat-turn user">{{ pending }}</p><p v-if="busy" class="chat-thinking" role="status">小寻正在思考 · · ·</p>
          <AgentTaskPanel v-if="auth.user" ref="taskPanel" :task="task??emptyTask" :photos="attachedPhotos" @published="clearPhotos" @exclude="exclude" @progress="taskProgress" />
        </div>
        <div v-if="attachedPhotos.length" class="chat-attachments" aria-label="待发布照片"><div v-for="photo in attachedPhotos" :key="photo.key"><img :src="photo.url" alt="待发布实拍照片"/><button type="button" :disabled="busy" @click="removePhoto(photo.key)">移除照片</button></div></div><p v-if="error" class="chat-error" role="alert">{{ error }}</p>
        <section v-if="photoObservation" class="chat-photo-review"><label>先核对照片里的外观<textarea v-model="photoObservation" maxlength="1000" rows="3"/></label><button type="button" @click="photoObservation=''">放弃这次识别</button><button type="button" @click="acceptPhoto">外观正确，帮我查找</button></section>
        <div v-if="!auth.user" class="chat-login"><RouterLink to="/login?redirect=/home">登录后和小寻交流</RouterLink><span>也可以直接在工作台描述物品。</span></div>
        <form v-else class="xun-chat-compose" @submit.prevent="send"><label class="visually-hidden" for="xun-chat-input">告诉小寻你记得的情况</label><textarea id="xun-chat-input" ref="entry" v-model="input" rows="2" maxlength="1200" :disabled="busy" placeholder="例如：昨天自习后耳机不见了，记不清在哪儿…" @keydown.enter.exact="!$event.isComposing && ($event.preventDefault(), send())"/><input ref="photoInput" type="file" hidden accept="image/jpeg,image/png,image/webp" @change="photo"/><div class="compose-actions"><button type="button" :disabled="busy || !turns.length" @click="reset">新一轮</button><button type="button" :disabled="busy" @click="photoInput?.click()">照片</button><button type="button" class="voice-button" :disabled="busy" :aria-pressed="voiceEnabled" @click="speak">{{ voiceLoading ? '准备声音…' : voiceEnabled ? '关闭声音' : '开启声音' }}</button><button v-if="busy" type="button" @click="cancel">停止等待</button><button v-else type="submit" class="chat-send" :disabled="!input.trim()">发送 ↑</button></div></form>
      </section>
    </div>
  </Teleport>
</template>

<style>
.chat-photo-review{margin:0 16px 10px;padding:12px;background:#f1f7ff;border:1px solid #d6e4f7;border-radius:12px;max-height:220px;overflow:auto;font-size:12px;color:#39597b}.chat-photo-review label{display:grid;gap:8px}.chat-photo-review textarea{width:100%;box-sizing:border-box;border:1px solid #ccdef4;border-radius:9px;padding:9px;font:inherit;resize:vertical}.chat-photo-review button{margin:8px 8px 0 0;border:0;border-radius:8px;background:#e1edff;color:#2468cf;padding:7px 9px;cursor:pointer}
.xun-companion{display:flex;align-items:center;gap:26px;min-height:210px;margin:6px 0 20px;padding:12px 32px;background:linear-gradient(110deg,#f8fcff,#fff 65%);border:1px solid #d9e8fa;border-radius:22px}.agent-stage{position:relative;flex:0 0 175px;height:205px;display:grid;place-items:center}.agent-character{position:relative;z-index:2;width:150px;height:198px;padding:0;border:0;background:none;cursor:pointer}.agent-character:hover{filter:drop-shadow(0 0 12px #5f9ff83b)}.agent-character:focus-visible{outline:2px solid #2877e9;border-radius:20px}.agent-platform{position:absolute;bottom:4px;left:12px;right:12px;height:24px;border:1px solid #b9d4f5;background:#e6f0fc;border-radius:50%;box-shadow:0 6px 0 #d2e2f6}.agent-bubble{position:absolute;z-index:4;left:110px;top:5px;width:220px;padding:12px 15px;border:1px solid #d3e4f8;border-radius:16px 16px 16px 3px;background:white;box-shadow:0 8px 22px #1d61a713;color:#426487;font-size:12px;line-height:1.7;pointer-events:none}.agent-label{font-size:12px;color:#2a75d9;font-weight:700}.agent-intro h3{font-size:23px;color:#17365c;line-height:1.5;margin:9px 0}.agent-intro p{font-size:13px;color:#667c96;line-height:1.8;margin:0 0 15px}.agent-open{border:0;border-radius:22px;background:#226ce7;color:#fff;padding:10px 18px;font-weight:700;cursor:pointer}.bubble-enter-active,.bubble-leave-active{transition:opacity .3s,transform .3s}.bubble-enter-from,.bubble-leave-to{opacity:0;transform:translateY(5px)}
.xun-chat-backdrop{position:fixed;inset:0;z-index:1500;display:flex;justify-content:flex-end;align-items:stretch;padding:24px;background:#0c24423b;backdrop-filter:blur(5px)}.xun-chat{display:flex;flex-direction:column;width:min(460px,100%);max-height:100%;border:1px solid #d3e2f5;border-radius:24px;background:#f6f9fe;box-shadow:0 25px 80px #0a294338;overflow:hidden;color:#203a59;outline:none;font-family:inherit}.xun-chat-header{display:flex;align-items:center;gap:12px;padding:12px 20px;background:white;border-bottom:1px solid #e2ebf6}.chat-mini-agent{width:46px;height:60px}.xun-chat-header h2{margin:0;font-size:19px}.xun-chat-header p{margin:5px 0 0;font-size:12px;color:#7b8da4}.chat-close{margin-left:auto;align-self:flex-start;border:0;background:none;font-size:28px;color:#73869e;cursor:pointer;padding:4px 8px}.xun-chat-messages{flex:1;min-height:100px;overflow:auto;padding:20px;display:flex;flex-direction:column;gap:14px}.chat-turn{margin:0;max-width:90%;padding:12px 15px;border-radius:16px;font-size:14px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere}.chat-turn.assistant{align-self:flex-start;background:#fff;border:1px solid #e0e9f6;border-bottom-left-radius:4px}.chat-turn.user{align-self:flex-end;background:#246ae4;color:white;border-bottom-right-radius:4px}.chat-thinking{font-size:12px;color:#6281a5;margin:0}.chat-draft{margin:0 16px 10px;padding:13px 15px;border-radius:14px;border:1px solid #b9dfd6;background:#f1fcf8;max-height:240px;overflow:auto}.chat-draft>div{display:flex;justify-content:space-between;font-size:12px;gap:10px}.chat-draft>div span{color:#21876f}.chat-draft p{font-size:12px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere}.chat-draft button{font-size:12px;border:0;background:none;color:#197b64;cursor:pointer;padding:4px 0;margin-right:12px}.chat-draft .chat-continue{font-weight:700}.chat-error{color:#a34637;background:#fff0ed;padding:10px 15px;margin:0 16px 8px;border-radius:10px;font-size:12px;line-height:1.6}.xun-chat-compose{padding:12px 16px 16px;background:#fff;border-top:1px solid #e2eaf5}.xun-chat-compose textarea{display:block;resize:vertical;min-height:60px;max-height:160px;width:100%;box-sizing:border-box;border:1px solid #d6e2f3;border-radius:13px;background:#f8faff;padding:11px 13px;outline:none;font:inherit;font-size:13px;line-height:1.6;color:#294564}.xun-chat-compose textarea:focus{border-color:#2875eb}.compose-actions{display:flex;align-items:center;gap:7px;margin-top:9px}.compose-actions button{border:0;background:#f1f5fc;color:#567596;padding:8px 10px;border-radius:10px;font-size:12px;cursor:pointer}.compose-actions button:disabled{opacity:.45;cursor:default}.compose-actions .chat-send{margin-left:auto;background:#246ae4;color:white}.chat-login{display:grid;gap:10px;padding:20px;text-align:center;background:white}.chat-login a{color:#246ae4;font-weight:700}.chat-login span{font-size:12px;color:#7b8da4}
@media(max-width:600px){.xun-companion{gap:10px;padding:8px 12px;min-height:185px}.agent-stage{flex-basis:100px;height:175px}.agent-character{width:112px;height:165px}.agent-platform{left:0;right:0;bottom:6px}.agent-bubble{width:165px;left:48px;top:0;font-size:11px;padding:9px 11px}.agent-intro h3{font-size:17px}.agent-intro p{font-size:11px}.agent-label{font-size:10px}.agent-open{font-size:12px;padding:9px 12px}.xun-chat-backdrop{padding:0}.xun-chat{width:100%;border-radius:0;max-height:100dvh}.xun-chat-header{padding-top:max(12px,env(safe-area-inset-top))}.xun-chat-compose{padding-bottom:max(16px,env(safe-area-inset-bottom))}.chat-draft{max-height:180px}}
@media(prefers-reduced-motion:reduce){.bubble-enter-active,.bubble-leave-active{transition:none}}
</style>
