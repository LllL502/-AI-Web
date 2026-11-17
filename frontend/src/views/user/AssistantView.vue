<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api, ApiError, readableApiError } from '../../api/client'
import AssistantCompanion from '../../components/AssistantCompanion.vue'
import { takeAssistantImage } from '../../stores/assistantDraft'

type Kind = 'LOST' | 'FOUND'
type StageStatus = 'completed' | 'waiting' | 'blocked'

interface Draft {
  kind: Kind
  title: string
  category_hint: string
  brand: string
  colors: string[]
  occurred_at: string | null
  location_hint: string
  public_description: string
  uncertain_fields: string[]
  source_spans: Record<string, string>
}

interface Stage {
  id: string
  label: string
  status: StageStatus
}

interface FollowUp {
  field: string
  question: string
  reason: string
  required: boolean
}

interface Candidate {
  ranking?: { score: number; factors: Record<string, number | null>; penalty_multiplier: number; conflicts: string[] }
  image_note?: string
  id: string
  citation_id: string
  title: string
  description: string
  category: string
  brand: string
  color: string
  occurred_at: string
  location: string
  image_url: string
  url: string
  reasons: string[]
}

interface PrepareResponse {
  data: {
    workflow_id: string
    provider: { name: string; model: string; simulated: boolean }
    stages: Stage[]
    draft: Draft
    follow_up_questions: FollowUp[]
  }
}

interface SearchResponse {
  data: {
    retrieval_method: string
    semantic_retrieval: boolean
    message: string
    candidates: Candidate[]
    stations: Array<{ id: number; name: string; address: string; public_location: string }>
    stages: Stage[]
  }
}

interface CapabilitiesResponse {
  data: {
    provider: { mode: string; simulated: boolean; configured: boolean }
    inputs: { text: boolean; image: boolean }
    guardrails: string[]
  }
}

const route = useRoute()
const companion=ref<InstanceType<typeof AssistantCompanion>>()
const kind = ref<Kind>('LOST')
const description = ref('')
const selectedImage = ref<File | null>(null)
const imageObservation = ref('')
const imageBusy = ref(false)
const semanticUsed = ref(false)

function selectImage(event: Event) {
  selectedImage.value = (event.target as HTMLInputElement).files?.[0] ?? null
  imageObservation.value = ''
}

async function understandImage() {
  if (!selectedImage.value || imageBusy.value) return
  if (selectedImage.value.size > 8 * 1024 * 1024) {
    error.value = '图片不能超过 8MB。'
    return
  }
  imageBusy.value = true
  error.value = ''
  const controller = new AbortController()
  activeController = controller
  const timer = window.setTimeout(() => controller.abort(), 90_000)
  try {
    const form = new FormData()
    form.append('image', selectedImage.value)
    const response = await api<{data: {observation: string}}>('/assistant/image/', {
      method: 'POST', body: form, signal: controller.signal,
    })
    imageObservation.value = response.data.observation
  } catch (reason) {
    error.value = readableApiError(reason, '图片理解失败，请检查本地模型。')
  } finally {
    window.clearTimeout(timer)
    imageBusy.value = false
    if (activeController === controller) activeController = null
  }
}

function acceptObservation() {
  description.value = (description.value + '\n图片观察（已人工核对）：' + imageObservation.value).trim().slice(0, 1200)
  imageObservation.value = ''
  draft.value = null
  candidates.value = []
  retrievalMessage.value = ''
}
const draft = ref<Draft | null>(null)
const colorText = ref('')
const followUps = ref<FollowUp[]>([])
const stages = ref<Stage[]>([])
const candidates = ref<Candidate[]>([])
const stations = ref<Array<{ id: number; name: string; address: string; public_location: string }>>([])
const capabilities = ref<CapabilitiesResponse['data'] | null>(null)
const provider = ref<PrepareResponse['data']['provider'] | null>(null)
const retrievalMessage = ref('')
const error = ref('')
const statusMessage = ref('')
const phase = ref<'idle' | 'preparing' | 'confirming' | 'retrieving' | 'complete' | 'error'>('idle')
const lastAction = ref<'prepare' | 'search'>('prepare')
let activeController: AbortController | null = null
let requestTimedOut = false

const busy = computed(() => imageBusy.value || phase.value === 'preparing' || phase.value === 'retrieving')
const simulated = computed(() => provider.value?.simulated ?? capabilities.value?.provider.simulated ?? false)
const imagePending = computed(() => capabilities.value ? !capabilities.value.inputs.image : true)

onMounted(async () => {
  const requestedKind = route.query.kind
  if (requestedKind === 'LOST' || requestedKind === 'FOUND') kind.value = requestedKind
  const requestedDescription = route.query.description
  if (typeof requestedDescription === 'string') description.value = requestedDescription.slice(0, 1200)
  const queuedImage = takeAssistantImage()
  if (queuedImage) selectedImage.value = queuedImage

  try {
    capabilities.value = (await api<CapabilitiesResponse>('/assistant/capabilities/')).data
  } catch {
    // 不让能力说明失败阻断普通表单兜底。
  }
})

onBeforeUnmount(() => activeController?.abort())

function cancelRequest() {
  if (!activeController) return
  activeController.abort()
  statusMessage.value = '已取消本次请求，未写入任何业务数据。'
}

async function requestWithTimeout<T>(path: string, body: unknown): Promise<T> {
  activeController?.abort()
  const controller = new AbortController()
  activeController = controller
  requestTimedOut = false
  const timer = window.setTimeout(() => {
    requestTimedOut = true
    controller.abort()
  }, 120_000)
  try {
    return await api<T>(path, {
      method: 'POST',
      body: JSON.stringify(body),
      signal: controller.signal,
    })
  } finally {
    window.clearTimeout(timer)
    if (activeController === controller) activeController = null
  }
}

function requestError(reason: unknown, fallback: string) {
  if (reason instanceof ApiError && reason.code === 'request_aborted') {
    return requestTimedOut
      ? '请求已超过 120 秒并自动取消，可重试或使用普通表单。'
      : '请求已取消，可重新开始。'
  }
  return readableApiError(reason, fallback)
}

async function prepare() {
  if (description.value.trim().length < 5) {
    error.value = '请至少输入 5 个字，说明丢了或拾到什么。'
    return
  }
  lastAction.value = 'prepare'
  phase.value = 'preparing'
  error.value = ''
  statusMessage.value = '正在结构化描述…'
  candidates.value = []
  retrievalMessage.value = ''
  try {
    const response = await requestWithTimeout<PrepareResponse>('/assistant/prepare/', {
      kind: kind.value,
      description: description.value.trim(),
    })
    draft.value = response.data.draft
    colorText.value = response.data.draft.colors.join('、')
    provider.value = response.data.provider
    followUps.value = response.data.follow_up_questions
    stages.value = response.data.stages
    phase.value = 'confirming'
    statusMessage.value = '已生成待确认字段。请修正后再检索，系统不会自动发布或认领。'
  } catch (reason) {
    error.value = requestError(reason, '暂时无法结构化描述。')
    phase.value = 'error'
    statusMessage.value = ''
  }
}

function confirmedDraft(): Draft | null {
  if (!draft.value) return null
  return {
    ...draft.value,
    kind: kind.value,
    colors: colorText.value.split(/[,，、\s]+/).map((value) => value.trim()).filter(Boolean).slice(0, 5),
    occurred_at: draft.value.occurred_at || null,
  }
}

async function searchCandidates() {
  const confirmed = confirmedDraft()
  if (!confirmed) return
  lastAction.value = 'search'
  phase.value = 'retrieving'
  error.value = ''
  statusMessage.value = '正在当前校区的真实公开记录中检索…'
  try {
    const response = await requestWithTimeout<SearchResponse>('/assistant/search/', {
      draft: confirmed,
      limit: 5,
    })
    candidates.value = response.data.candidates
    semanticUsed.value = response.data.semantic_retrieval
    stations.value = response.data.stations
    stages.value = response.data.stages
    retrievalMessage.value = response.data.message
    phase.value = 'complete'
    statusMessage.value = '检索完成。所有候选都可打开原始公开记录核对。'
  } catch (reason) {
    error.value = requestError(reason, '真实候选检索失败。')
    phase.value = 'error'
    statusMessage.value = ''
  }
}

function retry() {
  if (lastAction.value === 'search' && draft.value) void searchCandidates()
  else void prepare()
}
</script>

<template>
  <div class="page assistant-page">
    <header class="assistant-hero">
      <p class="eyebrow">AI 寻物</p>
      <h1>从一点印象，找到线索。</h1>
    </header>

    <p v-if="simulated" class="mode-banner" role="status">
      <strong>开发模式</strong>
      当前结构化结果由本地规则桩生成，不是真实大模型输出，不会产生外部请求或费用。
    </p>

    <div class="assistant-grid">
      <section class="panel input-panel">
        <h2>手动整理线索</h2>
        <form @submit.prevent="prepare">
          <fieldset class="kind-switch">
            <legend>你遇到的是</legend>
            <label><input v-model="kind" type="radio" value="LOST" /> 我丢了物品</label>
            <label><input v-model="kind" type="radio" value="FOUND" /> 我拾到物品</label>
          </fieldset>
          <label class="description-field">
            <span>一句话描述</span>
            <textarea v-model="description" maxlength="1200" rows="7" placeholder="例如：昨天晚上可能在图书馆丢了一副黑色 Sony 耳机，充电盒上有一道划痕。"></textarea>
          </label>
          <div class="actions">
            <button v-if="busy" class="button button-ghost" type="button" @click="cancelRequest">取消</button>
            <button class="button button-brand" type="submit" :disabled="busy">
              {{ phase === 'preparing' ? '正在提取…' : '提取待确认字段' }}
            </button>
          </div>
        </form>
        <section class="follow-ups">
          <h3>用照片补充外观特征</h3>
          <input aria-label="上传物品照片用于识别" type="file" accept="image/jpeg,image/png,image/webp" :disabled="imageBusy || busy" @change="selectImage" />
          <p v-if="selectedImage" class="selected-image-name">已选择：{{ selectedImage.name }}</p>
          <p v-if="imagePending" class="capability-note">尚未配置本地视觉服务，配置后可使用图片理解。</p>
          <button type="button" class="button button-ghost" :disabled="!selectedImage || imageBusy || busy || imagePending" @click="understandImage">{{ imageBusy ? '正在本机识别…' : '理解图片' }}</button>
          <button v-if="imageBusy" type="button" @click="cancelRequest">取消</button>
          <template v-if="imageObservation">
            <label>核对图片观察<textarea v-model="imageObservation" rows="4" maxlength="1000"></textarea></label>
            <button type="button" class="button button-brand" @click="acceptObservation">确认并加入描述</button>
          </template>
        </section>
        <RouterLink class="fallback-link" :to="kind === 'LOST' ? '/publish/lost' : '/publish/found'">
          不使用 AI，直接打开普通发布表单 →
        </RouterLink>
      </section>

      <aside v-if="stages.length || busy || error" class="panel workflow-panel" aria-label="执行进度">
        <h2>处理进度</h2>
        <ol v-if="stages.length">
          <li v-for="stage in stages" :key="stage.id" :class="stage.status">
            <span aria-hidden="true"></span>
            <div><strong>{{ stage.label }}</strong><small>{{ stage.status === 'completed' ? '已完成' : stage.status === 'waiting' ? '等待你确认' : '未执行' }}</small></div>
          </li>
        </ol>
        <p v-if="busy && statusMessage" class="status-message" aria-live="polite">{{ statusMessage }}</p>
        <div v-if="error" class="error-message" role="alert">
          <p>{{ error }}</p>
          <button class="button button-ghost" type="button" @click="retry">重试上一步</button>
        </div>
      </aside>
    </div>

    <section v-if="!draft" class="workspace-welcome panel">
      <div class="assistant-entry"><AssistantCompanion ref="companion" mode="text" :description="description" :kind="kind" :initial-photo="selectedImage" @apply="description=$event"/><h2>和小寻一起找回来</h2><p>丢失或拾到物品，都可以直接告诉我。</p><button class="button button-brand" type="button" @click="companion?.show()">和小寻聊聊</button></div>
    </section>

    <section v-if="draft" class="panel confirmation-panel">
      <div class="section-heading">
        <div><h2>确认物品信息</h2></div>
      </div>
      <div class="draft-grid">
        <label class="wide"><span>标题</span><input v-model="draft.title" maxlength="120" /></label>
        <label><span>类别提示</span><input v-model="draft.category_hint" maxlength="80" placeholder="不确定可留空" /></label>
        <label><span>品牌</span><input v-model="draft.brand" maxlength="80" placeholder="不确定可留空" /></label>
        <label><span>颜色（多个用顿号分隔）</span><input v-model="colorText" maxlength="120" /></label>
        <label><span>可能地点</span><input v-model="draft.location_hint" maxlength="160" /></label>
        <label><span>时间</span><input v-model="draft.occurred_at" type="datetime-local" /></label>
        <label class="wide"><span>公开描述</span><textarea v-model="draft.public_description" maxlength="3000" rows="5"></textarea></label>
      </div>
      <div v-if="followUps.length" class="follow-ups">
        <h3>可选补问</h3>
        <article v-for="question in followUps" :key="question.field">
          <strong>{{ question.question }}</strong>
        </article>
      </div>
      <div class="actions">
        <button class="button button-brand" type="button" :disabled="busy" @click="searchCandidates">
          {{ phase === 'retrieving' ? '正在检索…' : '我已确认，检索真实公开候选' }}
        </button>
      </div>
    </section>

    <section v-if="retrievalMessage" class="results-section">
      <div class="section-heading">
        <div><h2>值得核对的线索</h2></div>
      </div>
      <details class="method-notes"><summary>检索方式</summary><p>{{ semanticUsed ? '本地向量语义检索＋六因子重排' : '当前为公开记录关键词召回，语义和图片召回尚未启用' }}</p></details>
      <div v-if="candidates.length" class="candidate-list">
        <article v-for="(candidate,index) in candidates" :key="candidate.id" class="panel candidate-card" :class="{ 'without-image': !candidate.image_url }">
          <span class="rank">#{{ index + 1 }}</span>
          <img v-if="candidate.image_url" :src="candidate.image_url" :alt="candidate.title" />
          <div>
            <h3>{{ candidate.title }}</h3>
            <small v-if="candidate.image_note && candidate.image_url">{{ candidate.image_note }}</small>
            <p>{{ candidate.description }}</p>
            <dl><div><dt>类别</dt><dd>{{ candidate.category }}</dd></div><div><dt>公开地点</dt><dd>{{ candidate.location }}</dd></div></dl>
            <details v-if="candidate.ranking" class="ranking-evidence">
              <summary>查看排序依据 · 排序分 {{ candidate.ranking.score.toFixed(3) }}</summary>
              <p>排序分用于比较候选，不代表物品归属概率。</p>
              <ul><li v-for="reason in candidate.reasons" :key="reason">{{ reason }}</li></ul>
              <p v-for="(label, key) in { text: '语义', category: '类别', color: '颜色', brand: '品牌', time: '时间', location: '地点' }" :key="key">
                {{ label }}：{{ candidate.ranking.factors[key] == null ? '信息不足，未计分' : candidate.ranking.factors[key]!.toFixed(3) }}
              </p>
              <p v-if="candidate.ranking.conflicts.length">存在冲突，综合分乘以 {{ candidate.ranking.penalty_multiplier.toFixed(3) }}；请核对原始记录。</p>
            </details>
            <details class="method-notes"><summary>线索编号</summary><p class="citation">{{ candidate.citation_id }}</p></details>
            <RouterLink :to="candidate.url">打开原始公开记录核对 →</RouterLink>
          </div>
        </article>
      </div>
      <p v-else class="empty-result">暂时没有找到合适的线索，可以补充特征后再试。</p>
      <div v-if="stations.length" class="station-strip">
        <strong>当前校区可用服务站</strong>
        <span v-for="station in stations" :key="station.id">{{ station.name }}（{{ station.public_location }}）</span>
      </div>
    </section>
  </div>
</template>

<style scoped>
.candidate-card.without-image{grid-template-columns:1fr}.selected-image-name{margin:0 0 10px;color:var(--ct-text-muted);font-size:12px;overflow-wrap:anywhere}
.assistant-page{max-width:1180px}.assistant-hero{max-width:850px;margin-bottom:26px}.assistant-hero h1{max-width:820px;margin:8px 0 14px;font-size:clamp(34px,5vw,64px);line-height:1.05}.assistant-hero>p:last-child{max-width:760px;color:var(--ct-text-muted);line-height:1.8}.eyebrow{margin:0;color:var(--ct-brand);font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}.mode-banner{margin:0 0 20px;padding:14px 17px;border:1px solid rgba(192,139,28,.3);border-radius:12px;background:rgba(192,139,28,.08);color:#76540e;line-height:1.7}.mode-banner strong{margin-right:8px}.assistant-grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(280px,.75fr);gap:18px}.input-panel,.workflow-panel,.confirmation-panel{padding:28px}.input-panel h2,.workflow-panel h2{margin-top:0}.input-panel form{display:grid;gap:20px}.kind-switch{display:flex;gap:18px;margin:0;padding:0;border:0}.kind-switch legend,.description-field>span,.draft-grid label>span{display:block;margin-bottom:8px;color:var(--ct-text-muted);font-size:12px}.kind-switch label{display:flex;align-items:center;gap:7px}.description-field textarea,.draft-grid input,.draft-grid textarea{width:100%;padding:13px 14px;border:1px solid var(--ct-border);border-radius:11px;background:var(--ct-bg-soft);color:var(--ct-text);outline:0}.description-field textarea:focus,.draft-grid input:focus,.draft-grid textarea:focus{border-color:var(--ct-brand)}.description-field small,.capability-note{display:block;margin-top:8px;color:var(--ct-text-muted);font-size:12px;line-height:1.6}.actions{display:flex;justify-content:flex-end;gap:10px}.fallback-link{display:inline-block;margin-top:16px;color:var(--ct-brand);font-weight:700}.workflow-panel ol{display:grid;gap:14px;margin:22px 0;padding:0;list-style:none}.workflow-panel li{display:flex;gap:12px;align-items:center;color:var(--ct-text-muted)}.workflow-panel li>span{width:12px;height:12px;border:2px solid var(--ct-border);border-radius:50%}.workflow-panel li.completed>span{border-color:var(--ct-success);background:var(--ct-success)}.workflow-panel li.waiting>span{border-color:var(--ct-brand);box-shadow:0 0 0 4px rgba(141,48,46,.1)}.workflow-panel li strong,.workflow-panel li small{display:block}.workflow-panel li small{margin-top:3px;font-size:11px}.status-message{padding:12px;border-radius:10px;background:var(--ct-bg-soft);color:var(--ct-text-muted);line-height:1.6}.error-message{padding:14px;border-radius:10px;background:rgba(173,52,52,.08);color:var(--ct-danger)}.error-message p{margin-top:0}.confirmation-panel{margin-top:20px}.section-heading{display:flex;align-items:end;justify-content:space-between;gap:20px;margin-bottom:18px}.section-heading h2{margin:5px 0 0}.section-heading>small{max-width:420px;color:var(--ct-text-muted);text-align:right}.draft-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:17px}.draft-grid .wide{grid-column:1/-1}.follow-ups{margin:22px 0;padding:18px;border-left:3px solid var(--ct-brand);background:var(--ct-bg-soft)}.follow-ups h3{margin-top:0}.follow-ups article+article{margin-top:12px}.follow-ups p{margin:4px 0;color:var(--ct-text-muted);font-size:12px}.results-section{margin-top:34px}.retrieval-message,.empty-result{padding:16px;border:1px dashed var(--ct-border);border-radius:12px;color:var(--ct-text-muted)}.candidate-list{display:grid;gap:14px}.candidate-card{position:relative;display:grid;grid-template-columns:160px 1fr;gap:22px;padding:22px}.candidate-card>img{width:160px;height:160px;border-radius:12px;object-fit:cover}.candidate-card>.rank{position:absolute;top:12px;right:14px;color:var(--ct-brand);font-weight:800}.candidate-card h3{margin:4px 0 8px}.candidate-card p{color:var(--ct-text-muted)}.candidate-card .citation{margin:0;font-family:monospace;font-size:11px}.candidate-card dl{display:flex;gap:22px}.candidate-card dl div{display:flex;gap:7px}.candidate-card dt{color:var(--ct-text-muted)}.candidate-card dd{margin:0}.candidate-card ul{padding-left:18px;color:var(--ct-text-muted)}.candidate-card a{color:var(--ct-brand);font-weight:700}.station-strip{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px;padding:16px;border-radius:12px;background:var(--ct-bg-soft)}.station-strip span{padding-left:10px;border-left:1px solid var(--ct-border);color:var(--ct-text-muted)}
@media(max-width:820px){.assistant-grid,.draft-grid{grid-template-columns:1fr}.draft-grid .wide{grid-column:auto}.candidate-card{grid-template-columns:1fr}.candidate-card>img{width:100%;height:220px}.section-heading{align-items:flex-start;flex-direction:column}.section-heading>small{text-align:left}.kind-switch{align-items:flex-start;flex-direction:column}}
</style>
