<script setup lang="ts">
import {statusLabel} from '../../utils/statusLabels'
import {readableApiError} from '../../api/client'
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api, ApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'

type Candidate = {
  id: number
  rank: number
  final_score: string
  coverage: string
  is_actionable: boolean
  factors: { scores: Record<string, number | null>; contributions: Record<string, number> }
  explanation: { level: string; missing_factors: string[]; conflicts: string[]; text_terms: { term: string; contribution: number }[] }
  item: { id: string; title: string; category: string; location: string; business_status: string }
}
type Run = { id: number; query_item_id: string; status: string; candidate_count: number; config_version: string; index_version_name: string; created_at: string; candidates: Candidate[] }

const route = useRoute()
const run = ref<Run | null>(null)
const error = ref('')
const loading = ref(true)
const factors = [['text', '文本'], ['category', '类别'], ['location', '地点'], ['time', '时间'], ['color', '颜色'], ['brand', '品牌']]
const actionable = computed(() => run.value?.candidates.filter((entry) => entry.is_actionable).length ?? 0)

async function load() {
  try {
    const response = await api<{ data: Run }>(`/matches/runs/${route.params.runId}/`)
    run.value = response.data
  } catch (reason) {
    error.value = readableApiError(reason,'无法读取匹配报告')
  } finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <div class="page report">
    <p v-if="loading" class="empty">正在读取匹配结果…</p>
    <p v-else-if="error" class="empty error">{{ error }}</p>
    <template v-else-if="run">
      <header>
        <div><h1 class="page-title">匹配报告</h1></div>
        <dl><div><dt>候选</dt><dd>{{ run.candidate_count }}</dd></div><div><dt>可核查</dt><dd>{{ actionable }}</dd></div></dl>
      </header>
      <div v-if="run.candidates.length" class="candidates">
        <article v-for="entry in run.candidates" :key="entry.id" class="panel candidate">
          <div class="rank">#{{ entry.rank }}</div>
          <div class="candidate-main">
            <div class="candidate-head">
              <div><span class="status-tag">{{ entry.explanation.level }}</span><h2>{{ entry.item.title }}</h2><p>{{ entry.item.category }} · {{ entry.item.location }} · {{statusLabel(entry.item.business_status)}}</p></div>
              <div class="score"><strong>{{ (Number(entry.final_score) * 100).toFixed(1) }}</strong><span>分</span></div>
            </div>
            <div class="factor-grid"><div v-for="factor in factors" :key="factor[0]"><span>{{ factor[1] }}</span><strong>{{ entry.factors.scores[factor[0]] === null ? '缺失' : `${(Number(entry.factors.scores[factor[0]]) * 100).toFixed(0)}%` }}</strong><i><b :style="{ width: `${Number(entry.factors.contributions[factor[0]] ?? 0) * 100}%` }"></b></i></div></div>
            <p v-if="entry.explanation.conflicts.length" class="conflict">已知冲突：{{ entry.explanation.conflicts.join('、') }}</p>
            <footer><RouterLink :to="`/items/${entry.item.id}`">查看招领详情</RouterLink><RouterLink class="button button-ghost" :to="`/matches/compare/${run.query_item_id}/${entry.item.id}`">对比证据 <AppIcon name="arrow" /></RouterLink></footer>
          </div>
        </article>
      </div>
      <section v-else class="empty no-match">
        <div><AppIcon name="spark" /><h2>暂无符合条件的招领线索</h2><p>类别不同、时间次序不可能或相似度过低的信息已被排除，系统不会为了凑数展示无关候选。</p></div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.report header{display:grid;grid-template-columns:1fr auto;gap:30px;align-items:end}.report dl{display:flex;gap:1px;margin:0;background:var(--ct-border);border:1px solid var(--ct-border);border-radius:14px;overflow:hidden}.report dl div{padding:16px 22px;background:var(--ct-surface)}dt{color:var(--ct-text-muted);font-size:11px}dd{margin:5px 0 0;color:var(--ct-brand);font-size:24px;font-weight:800}.snapshot{display:flex;gap:18px;margin:30px 0;padding:13px 16px;color:var(--ct-text-muted);border-left:3px solid var(--ct-brand);background:rgba(141,48,46,.05);font-family:monospace}.candidates{display:grid;gap:14px}.candidate{display:grid;grid-template-columns:66px 1fr;overflow:hidden;box-shadow:none}.rank{display:grid;place-items:center;color:var(--ct-brand);font:700 18px monospace;background:var(--ct-bg-soft)}.candidate-main{padding:23px}.candidate-head{display:flex;justify-content:space-between;gap:24px}.candidate h2{margin:10px 0 4px}.candidate p{color:var(--ct-text-muted)}.score{text-align:right}.score strong{color:var(--ct-brand);font-size:36px}.score span,.score small{display:block;color:var(--ct-text-muted)}.factor-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-top:20px}.factor-grid div{padding:12px;border:1px solid var(--ct-border);border-radius:10px}.factor-grid span,.factor-grid strong{display:block;font-size:11px}.factor-grid strong{margin:5px 0}.factor-grid i{display:block;height:4px;background:var(--ct-bg);border-radius:4px}.factor-grid b{display:block;height:100%;background:var(--ct-brand)}.conflict{padding:10px;color:var(--ct-danger);background:rgba(173,52,52,.06)}.candidate footer{display:flex;justify-content:space-between;align-items:center;margin-top:20px;padding-top:15px;border-top:1px solid var(--ct-border)}.candidate footer>a:first-child{color:var(--ct-info)}.empty{display:grid;place-items:center;min-height:320px}.error{color:var(--ct-danger)}.no-match{text-align:center}.no-match svg{color:var(--ct-brand);font-size:34px}.no-match p{max-width:680px;color:var(--ct-text-muted)}
@media(max-width:850px){.factor-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:600px){.report header{grid-template-columns:1fr}.candidate{grid-template-columns:1fr}.rank{min-height:45px}.candidate-head{align-items:start}.factor-grid{grid-template-columns:repeat(2,1fr)}.snapshot{flex-direction:column}}
</style>
