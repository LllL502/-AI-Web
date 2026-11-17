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
const deleteBusy = ref<number | null>(null)
const error = ref('')

async function load() {
  try {
    const [itemResponse, runResponse] = await Promise.all([
      api<{ data: { items: OwnedItem[] } }>('/items/?kind=LOST&mine=true'),
      api<{ data: { items: Run[] } }>('/matches/runs/'),
    ])
    sources.value = itemResponse.data.items.filter(
      (item) => item.kind === 'LOST' && item.review_status === 'APPROVED',
    )
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
async function deleteRun(run: Run) {
  if (!window.confirm('确认删除这条匹配记录吗？已发布的失物信息不会被删除。')) return
  deleteBusy.value = run.id
  error.value = ''
  try {
    await api(`/matches/runs/${run.id}/`, { method: 'DELETE' })
    runs.value = runs.value.filter((entry) => entry.id !== run.id)
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '删除匹配记录失败'
  } finally { deleteBusy.value = null }
}
onMounted(load)
</script>

<template>
  <div class="page match-page">
    <header class="match-header"><h1 class="page-title">智能匹配</h1></header>
    <section class="run-panel panel"><div><label for="source">选择我的遗失信息</label><select id="source" v-model="selected"><option value="">请选择</option><option v-for="item in sources" :key="item.id" :value="item.id">{{ item.title }}</option></select><small v-if="!sources.length">暂无可匹配的遗失线索</small></div><button class="button button-brand" type="button" :disabled="busy || !selected" @click="runMatch"><AppIcon name="spark" />{{ busy ? '匹配中…' : '发起匹配' }}</button></section>
    <p v-if="error" class="message error">{{ error }}</p>
    <section class="runs"><div class="section-head"><h2>匹配记录</h2><span>{{ runs.length }} 次</span></div><div v-if="runs.length" class="run-list"><article v-for="run in runs" :key="run.id" class="run-row"><RouterLink :to="`/matches/runs/${run.id}`" class="run-link"><span class="run-id">#{{ run.id }}</span><div><strong>{{ sources.find(item => item.id === run.query_item_id)?.title ?? '历史源物品' }}</strong><small>{{ new Date(run.created_at).toLocaleString('zh-CN') }}</small></div><span class="status-tag">{{ run.status }}</span><strong>{{ run.candidate_count }} 个候选</strong><AppIcon name="arrow" /></RouterLink><button class="delete-run" type="button" :disabled="deleteBusy === run.id" @click="deleteRun(run)">{{ deleteBusy === run.id ? '删除中…' : '删除' }}</button></article></div><div v-else class="empty"><AppIcon name="spark" /><h3>暂无匹配记录</h3><p>选择一条遗失信息后即可开始匹配。</p></div></section>
  </div>
</template>

<style scoped>
.match-header { display: block; }.run-panel { display: grid; grid-template-columns: 1fr auto; gap: 18px; align-items: end; margin: 40px 0; padding: 24px; box-shadow: none; }.run-panel label { display: block; margin-bottom: 8px; color: var(--ct-text-muted); font-size: 12px; }.run-panel select { width: 100%; padding: 13px; color: var(--ct-text); border: 1px solid var(--ct-border); border-radius: 11px; background: var(--ct-bg-soft); }.section-head { display: flex; justify-content: space-between; align-items: center; }.section-head span { color: var(--ct-text-muted); font-size: 12px; }.run-list { overflow: hidden; border: 1px solid var(--ct-border); border-radius: 16px; }.run-row { display:flex;align-items:stretch;background:var(--ct-surface) }.run-row + .run-row { border-top: 1px solid var(--ct-border); }.run-link{display:grid;grid-template-columns:70px 1fr auto auto auto;gap:18px;align-items:center;min-width:0;flex:1;padding:18px}.run-row:hover { background: var(--ct-surface-raised); }.run-row small { display: block; margin-top: 4px; color: var(--ct-text-muted); }.run-id { color: var(--ct-brand); font-family: monospace; }.delete-run{align-self:center;margin-right:16px;padding:8px 10px;color:var(--ct-danger);border:0;border-radius:8px;background:transparent;cursor:pointer}.delete-run:hover{background:rgba(173,52,52,.08)}.delete-run:disabled{cursor:wait;opacity:.55}.empty { display: grid; place-items: center; min-height: 260px; color: var(--ct-text-muted); border: 1px dashed var(--ct-border); border-radius: 16px; text-align: center; }.empty > :first-child { color: var(--ct-brand); font-size: 35px; }.empty h3,.empty p { margin: 8px; }.message { padding: 13px; border-radius: 10px; }.message.error { color: var(--ct-danger); background: rgba(173,52,52,.08); }
@media (max-width: 760px) { .run-panel { grid-template-columns: 1fr; }.run-link { grid-template-columns: auto 1fr auto; }.run-link > :nth-child(4),.run-link > :nth-child(5) { display: none; }.delete-run{margin-right:8px} }
</style>
