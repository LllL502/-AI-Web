<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'

interface OwnedItem { id: string; title: string; kind: string; review_status: string }
interface Run { id: number; query_item_id: string; status: string; candidate_count: number; config_version: string; index_version_name: string; created_at: string }
const sources = ref<OwnedItem[]>([])
const runs = ref<Run[]>([])
const selected = ref('')
const busy = ref(false)
const error = ref('')

async function load() {
  try {
    const [itemResponse, runResponse] = await Promise.all([
      api<{ data: { items: OwnedItem[] } }>('/items/?kind=LOST&mine=true'),
      api<{ data: { items: Run[] } }>('/matches/runs/'),
    ])
    sources.value = itemResponse.data.items.filter((item) => item.kind === 'LOST')
    runs.value = runResponse.data.items
    selected.value ||= sources.value[0]?.id ?? ''
  } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '无法读取匹配数据' }
}
async function runMatch() {
  if (!selected.value) return
  busy.value = true; error.value = ''
  try {
    const response = await api<{ data: Run }>('/matches/runs/', { method: 'POST', body: JSON.stringify({ query_item_id: selected.value }) })
    runs.value.unshift(response.data)
  } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '匹配运行失败' }
  finally { busy.value = false }
}
onMounted(load)
</script>

<template>
  <div class="page match-page">
    <header class="match-header"><div><p class="eyebrow"><AppIcon name="spark" /> P09 · EXPLAINABLE MATCHING</p><h1 class="page-title">智能匹配</h1><p class="page-lead">真实调用后端 TF-IDF 索引、余弦相似度和六因子缺失感知评分。分数表示线索相似程度，不是所有权概率。</p></div><div class="model-badge"><span>初始模型</span><strong>TF-IDF + 6 Factors</strong><small>权重尚待验证集评估</small></div></header>
    <section class="run-panel panel"><div><label for="source">选择我的遗失信息</label><select id="source" v-model="selected"><option value="">请选择</option><option v-for="item in sources" :key="item.id" :value="item.id">{{ item.title }} · {{ item.review_status }}</option></select></div><button class="button button-brand" type="button" :disabled="busy || !selected" @click="runMatch"><AppIcon name="spark" />{{ busy ? '正在真实计算…' : '发起匹配' }}</button></section>
    <p v-if="error" class="message error">{{ error }}</p>
    <section class="runs"><div class="section-head"><h2>匹配运行</h2><span>{{ runs.length }} 次可追溯快照</span></div><div v-if="runs.length" class="run-list"><RouterLink v-for="run in runs" :key="run.id" :to="`/matches/runs/${run.id}`" class="run-row"><span class="run-id">#{{ run.id }}</span><div><strong>{{ sources.find(item => item.id === run.query_item_id)?.title ?? '历史源物品' }}</strong><small>{{ new Date(run.created_at).toLocaleString('zh-CN') }} · {{ run.config_version }}</small></div><span class="status-tag">{{ run.status }}</span><strong>{{ run.candidate_count }} 个候选</strong><AppIcon name="arrow" /></RouterLink></div><div v-else class="empty"><AppIcon name="spark" /><h3>尚无匹配运行</h3><p>先选择一条属于你的遗失信息，系统会保存算法和索引版本快照。</p></div></section>
    <aside class="formula"><span>缺失感知公式</span><code>S = Σ(wᵢ × mᵢ × Sᵢ) / Σ(wᵢ × mᵢ)</code><p>已知冲突以 0 分参与；未知信息才标记缺失。</p></aside>
  </div>
</template>

<style scoped>
.match-header { display: grid; grid-template-columns: 1fr auto; align-items: end; gap: 40px; }.model-badge { display: grid; gap: 4px; min-width: 250px; padding: 17px; border: 1px solid var(--ct-border-strong); border-radius: 14px; background: rgba(245,185,66,.06); }.model-badge span,.model-badge small { color: var(--ct-text-muted); font-size: 11px; }.model-badge strong { color: var(--ct-brand-strong); }.run-panel { display: grid; grid-template-columns: 1fr auto; gap: 18px; align-items: end; margin: 40px 0; padding: 24px; box-shadow: none; }.run-panel label { display: block; margin-bottom: 8px; color: var(--ct-text-muted); font-size: 12px; }.run-panel select { width: 100%; padding: 13px; color: var(--ct-text); border: 1px solid var(--ct-border); border-radius: 11px; background: var(--ct-bg-soft); }.section-head { display: flex; justify-content: space-between; align-items: center; }.section-head span { color: var(--ct-text-muted); font-size: 12px; }.run-list { overflow: hidden; border: 1px solid var(--ct-border); border-radius: 16px; }.run-row { display: grid; grid-template-columns: 70px 1fr auto auto auto; gap: 18px; align-items: center; padding: 18px; background: var(--ct-surface); }.run-row + .run-row { border-top: 1px solid var(--ct-border); }.run-row:hover { background: var(--ct-surface-raised); }.run-row small { display: block; margin-top: 4px; color: var(--ct-text-muted); }.run-id { color: var(--ct-brand); font-family: monospace; }.empty { display: grid; place-items: center; min-height: 260px; color: var(--ct-text-muted); border: 1px dashed var(--ct-border); border-radius: 16px; text-align: center; }.empty > :first-child { color: var(--ct-brand); font-size: 35px; }.empty h3,.empty p { margin: 8px; }.formula { display: grid; grid-template-columns: auto auto 1fr; gap: 18px; align-items: center; margin-top: 26px; padding: 17px; color: var(--ct-text-muted); border-left: 3px solid var(--ct-brand); background: rgba(245,185,66,.05); }.formula code { color: var(--ct-brand-strong); }.formula p { margin: 0; }.message { padding: 13px; border-radius: 10px; }.message.error { color: var(--ct-danger); background: rgba(255,111,120,.08); }
@media (max-width: 760px) { .match-header,.run-panel { grid-template-columns: 1fr; }.run-row { grid-template-columns: auto 1fr auto; }.run-row > :nth-child(4),.run-row > :nth-child(5) { display: none; }.formula { grid-template-columns: 1fr; } }
</style>
