<script setup lang="ts">
import { ref, onMounted, watch, onBeforeUnmount, nextTick } from 'vue'
import { api } from '../api/client'
import { useAuthStore } from '../stores/auth'
interface Campus { id:number; name:string; verification_status?:string }
interface School { id:number; name:string; province:string; city:string; is_demo:boolean; campuses:Campus[] }
const open = ref(false), query = ref(''), loading = ref(false), error = ref('')
const schools = ref<School[]>([]), chosen = ref<School|null>(null), selected = ref('')
const label = ref('选择学校与校区'), page = ref(1), pages = ref(1), total = ref(0)
const searchInput = ref<HTMLInputElement|null>(null), trigger = ref<HTMLButtonElement|null>(null)
const auth = useAuthStore()
const feedbackOpen=ref(false), feedbackName=ref(''), feedbackDetail=ref(''), feedbackSource=ref(''), feedbackMessage=ref(''), sending=ref(false)
const reviews=ref<{id:number;school_name:string;campus_name:string;detail:string;source_url:string}[]>([])
const reviewSource=ref(''),reviewNote=ref('')
async function sendFeedback(){
  if(!chosen.value)return
  sending.value=true;feedbackMessage.value=''
  try{await api('/stations/campus-feedback/',{method:'POST',body:JSON.stringify({school:chosen.value.id,campus_name:feedbackName.value,detail:feedbackDetail.value,source_url:feedbackSource.value})});feedbackMessage.value='已提交，管理员核对后更新校区目录。';feedbackName.value='';feedbackDetail.value='';feedbackSource.value=''}
  catch{feedbackMessage.value='提交失败，请确认已登录、填写校区名称及说明，来源链接应为完整网址。'}finally{sending.value=false}
}
async function loadReviews(){try{const result=await api<{data:{items:typeof reviews.value}}>('/stations/campus-feedback/review/');reviews.value=result.data.items}catch{feedbackMessage.value='无法读取待审核反馈'}}
async function reviewFeedback(id:number,decision:string){
  sending.value=true
  try{await api('/stations/campus-feedback/review/',{method:'POST',body:JSON.stringify({id,decision,source_url:reviewSource.value,note:reviewNote.value})});await loadReviews();feedbackMessage.value='处理已保存并记录审计'}catch{feedbackMessage.value='处理失败；采纳时必须填写核实后的来源网址。'}finally{sending.value=false}
}
let timer:ReturnType<typeof setTimeout>|undefined
let revision = 0
async function search(number=1) {
  const current = ++revision
  loading.value=true; error.value=''
  try {
    const result = await api<{data:{schools:School[];page:number;pages:number;total:number}}>(`/stations/campuses/?q=${encodeURIComponent(query.value)}&page=${number}`)
    if(current!==revision)return
    schools.value=result.data.schools; page.value=result.data.page; pages.value=result.data.pages; total.value=result.data.total
  } catch { if(current===revision)error.value='学校目录加载失败，请重试。' }
  finally { if(current===revision)loading.value=false }
}
watch(query,()=>{clearTimeout(timer);timer=setTimeout(()=>search(),250)})
onBeforeUnmount(()=>{clearTimeout(timer);revision++})
onMounted(async()=>{
  try {
    const campus=localStorage.getItem('campustrace-campus')
    const result=await api<{data:{schools:School[]}}>(`/stations/campuses/?${campus?`current_campus=${encodeURIComponent(campus)}`:'q=演示学校'}`)
    const school=result.data.schools[0]
    const entry=school?.campuses.find(c=>campus?String(c.id)===campus:true)
    if(school&&entry) label.value=`${school.name} · ${entry.name}`
  } catch { label.value='选择学校与校区' }
})
async function show(){open.value=true;await nextTick();searchInput.value?.focus();search()}
function choose(school:School){chosen.value=school;selected.value=school.campuses.length===1?String(school.campuses[0]!.id):'';feedbackOpen.value=false;feedbackMessage.value=''}
function confirm(){
  if(!chosen.value?.campuses.some(c=>String(c.id)===selected.value))return
  localStorage.setItem('campustrace-campus',selected.value)
  window.location.assign('/home')
}
function close(){open.value=false;trigger.value?.focus()}
function keyboard(event:KeyboardEvent){
  if(event.key==='Escape')close()
  if(event.key==='Tab'){
    const nodes=Array.from((event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('button:not(:disabled),input,select'))
    const first=nodes[0],last=nodes[nodes.length-1]
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}
  }
}
</script>
<template>
  <button ref="trigger" class="campus-trigger" @click="show" aria-haspopup="dialog" :aria-expanded="open">{{label}} <span>⌄</span></button>
  <Teleport to="body"><div v-if="open" class="campus-overlay" @click.self="close">
    <section class="campus-dialog" role="dialog" aria-modal="true" aria-labelledby="campus-title" @keydown="keyboard">
      <header><div><small>选择你的校园</small><h2 id="campus-title">学校与校区</h2></div><button @click="close" aria-label="关闭校园选择">×</button></header>
      <label class="search-label">搜索学校<input ref="searchInput" v-model="query" placeholder="学校名称、简称或拼音首字母，例如 XJTU" /></label>
      <div class="campus-columns"><section><p class="subheading">学校目录 · {{total}} 个结果</p>
        <p v-if="loading" role="status">正在搜索…</p><p v-else-if="error" role="alert">{{error}} <button @click="search()">重试</button></p>
        <div v-else class="school-results"><button v-for="school in schools" :key="school.id" :class="{selected:chosen?.id===school.id}" @click="choose(school)"><strong>{{school.name}}</strong><small>{{school.is_demo?'演示数据':`${school.province} · ${school.city}`}}</small></button><p v-if="!schools.length">未找到学校，请尝试完整名称。</p></div>
        <div class="pagination"><button :disabled="page<=1||loading" @click="search(page-1)">上一页</button><span>{{page}} / {{pages}}</span><button :disabled="page>=pages||loading" @click="search(page+1)">下一页</button></div>
      </section><section class="campus-results"><p class="subheading">{{chosen?.name??'先选择学校'}}</p>
        <template v-if="chosen"><label v-if="chosen.campuses.length">选择校区<select v-model="selected"><option value="">请选择校区</option><option v-for="campus in chosen.campuses" :key="campus.id" :value="String(campus.id)">{{campus.name}}{{campus.verification_status==='UNVERIFIED'?'（资料待核实）':''}}</option></select></label><div v-if="!chosen.campuses.length||chosen.campuses.some(c=>c.verification_status==='UNVERIFIED')" class="pending"><strong>校区资料待核实</strong><p>“主校区”是临时分组，尚未核实实际名称与位置。你可以反馈真实校区帮助完善。</p></div>
          <button class="button button-ghost" type="button" @click="feedbackOpen=!feedbackOpen">反馈校区 / 我要反映</button>
          <form v-if="feedbackOpen&&auth.user" class="feedback-form" @submit.prevent="sendFeedback"><label>校区名称<input v-model="feedbackName" required maxlength="100" placeholder="新增校区或需要更正的名称" /></label><label>反馈说明<textarea v-model="feedbackDetail" required maxlength="2000" placeholder="说明校区位置、别名或已有目录的问题" /></label><label>学校官网来源（选填）<input v-model="feedbackSource" type="url" placeholder="https://…" /></label><button class="button button-brand" :disabled="sending">提交反馈</button></form>
          <p v-else-if="feedbackOpen">请先<a href="/login?redirect=/home">登录</a>后提交反馈。</p>
        </template>
        <p v-else>搜索并选择学校后，这里会显示该校的校区。</p>
      </section></div>
      <p v-if="feedbackMessage" role="status">{{feedbackMessage}}</p>
      <section v-if="auth.user?.role==='ADMIN'" class="review-panel"><button class="button button-ghost" @click="loadReviews">管理校区反馈</button><template v-if="reviews.length"><label>核实后的来源网址<input v-model="reviewSource" type="url" /></label><label>审核说明<input v-model="reviewNote" /></label><article v-for="entry in reviews" :key="entry.id"><strong>{{entry.school_name}} · {{entry.campus_name}}</strong><p>{{entry.detail}}</p><p>用户提供来源：{{entry.source_url||'未提供'}}</p><button :disabled="sending||!reviewSource" @click="reviewFeedback(entry.id,'APPROVE')">采纳</button><button :disabled="sending" @click="reviewFeedback(entry.id,'REJECT')">不采纳</button></article></template></section>
      <footer><span>切换后只浏览和匹配所选校区的信息</span><button class="button button-brand" :disabled="!selected" @click="confirm">确认切换</button></footer>
    </section>
  </div></Teleport>
</template>
<style scoped>
.campus-trigger{max-width:230px;padding:11px 14px;border:1px solid var(--ct-border);border-radius:11px;background:var(--ct-bg);color:var(--ct-text);cursor:pointer;text-align:left;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.campus-trigger span{margin-left:8px}.campus-overlay{position:fixed;inset:0;z-index:1000;display:grid;place-items:center;padding:20px;background:#030a14cc;backdrop-filter:blur(8px)}.campus-dialog{width:min(860px,100%);max-height:90vh;overflow:auto;padding:26px;border:1px solid var(--ct-border);border-radius:22px;background:var(--ct-surface);color:var(--ct-text);box-shadow:var(--ct-shadow)}header,footer,.pagination{display:flex;justify-content:space-between;align-items:center;gap:12px}header h2{margin:5px 0 20px}header small,.subheading,footer span{color:var(--ct-text-muted)}header button{font-size:28px}.search-label input,select{width:100%;padding:13px;margin-top:8px;background:var(--ct-bg);border:1px solid var(--ct-border);border-radius:10px;color:var(--ct-text)}.campus-columns{display:grid;grid-template-columns:1.2fr 1fr;gap:24px;margin:18px 0}.school-results{height:290px;overflow:auto}.school-results button{display:block;width:100%;padding:12px;text-align:left;border:1px solid transparent;border-radius:9px;background:transparent;color:var(--ct-text);cursor:pointer}.school-results button:hover,.school-results .selected{border-color:var(--ct-brand);background:#f5b94212}.school-results small{display:block;margin-top:4px;color:var(--ct-text-muted)}.campus-results{padding:0 18px;border-left:1px solid var(--ct-border)}.pending{padding:16px;border-radius:12px;background:var(--ct-bg)}.pending p,.campus-results>p{line-height:1.8;color:var(--ct-text-muted)}.pagination button,header button{background:transparent;color:var(--ct-text);border:0;cursor:pointer}.pagination{margin-top:12px}footer{padding-top:18px;border-top:1px solid var(--ct-border)}footer span{font-size:12px}@media(max-width:640px){.campus-columns{grid-template-columns:1fr}.school-results{height:180px}.campus-results{border-left:0;border-top:1px solid var(--ct-border);padding:12px 0}.campus-dialog{padding:18px}.campus-trigger{max-width:180px;font-size:11px}footer{align-items:flex-end}}
</style>
<style scoped>
.feedback-form{display:grid;gap:12px;margin-top:16px}.feedback-form input,.feedback-form textarea,.review-panel input{display:block;width:100%;margin-top:6px;padding:10px;border:1px solid var(--ct-border);border-radius:8px;background:var(--ct-bg);color:var(--ct-text)}.feedback-form textarea{min-height:90px}.review-panel article{padding:12px;border-top:1px solid var(--ct-border)}.pending{margin:12px 0}.feedback-form label,.review-panel label{font-size:12px;color:var(--ct-text-muted)}
</style>
