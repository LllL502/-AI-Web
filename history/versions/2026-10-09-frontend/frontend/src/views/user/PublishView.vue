<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, ApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'
import AMapCampus from '../../components/AMapCampus.vue'

const props = defineProps<{ kind: 'LOST' | 'FOUND' }>()
const router = useRouter()
const step = ref(1)
const saving = ref(false)
const error = ref('')
const success = ref('')
const categories = ref<{ id: number; name: string; parent_id: number | null }[]>([])
const locations = ref<{ id: number; name: string; parent_id: number | null }[]>([])
const stations = ref<{ id: number; name: string; status: string }[]>([])
const form = reactive({ title: '', category: '', description: '', brand: '', color: '', occurred_at: '', location: '', location_detail: '', station: '' })
const point=ref<{latitude:number;longitude:number}|null>(null)
const draftKey = computed(() => `campustrace-draft-${localStorage.getItem('campustrace-campus')??'demo'}-${props.kind.toLowerCase()}`)
async function pickPoint(value:{latitude:number;longitude:number}){
  point.value={latitude:Number(value.latitude.toFixed(6)),longitude:Number(value.longitude.toFixed(6))}
  if(!form.location){
    try{
      const result=await api<{data:{id:number;name:string}}>('/maps/campus-region/',{method:'POST'})
      if(!locations.value.some(entry=>entry.id===result.data.id))locations.value.push({...result.data,parent_id:null})
      form.location=String(result.data.id)
    }catch(reason){error.value=reason instanceof ApiError?reason.message:'无法建立公开校园区域，请选择文字地点'}
  }
}

onMounted(async () => {
  const stored = localStorage.getItem(draftKey.value)
  if (stored) Object.assign(form, JSON.parse(stored))
  try {
    const response = await api<{ data: { categories: typeof categories.value; locations: typeof locations.value; stations: typeof stations.value } }>('/items/metadata/')
    categories.value = response.data.categories.filter((entry) => entry.parent_id !== null)
    const children=response.data.locations.filter((entry) => entry.parent_id !== null)
    locations.value = children.length?children:response.data.locations
    stations.value = response.data.stations
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '无法读取分类和地点字典'
  }
})
watch(form, () => localStorage.setItem(draftKey.value, JSON.stringify(form)), { deep: true })

async function save(submit = false) {
  saving.value = true; error.value = ''; success.value = ''
  try {
    const coordinates=point.value?{...point.value,coordinate_system:'GCJ02'}:{}
    const response = await api<{ data: { id: string } }>('/items/', { method: 'POST', body: JSON.stringify({ ...form, ...coordinates, station:form.station||null, kind: props.kind }) })
    if (submit) await api(`/items/${response.data.id}/submit/`, { method: 'POST' })
    localStorage.removeItem(draftKey.value)
    success.value = submit ? '已提交审核，公开前会由协调员检查隐私与内容完整性。' : '草稿已安全保存。'
    if (submit) setTimeout(() => router.push('/me/items'), 900)
  } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '保存失败，请检查后端服务与必填字段。' }
  finally { saving.value = false }
}
</script>

<template>
  <div class="page publish-page">
    <header><p class="eyebrow">{{ kind === 'LOST' ? 'P06 · LOST REPORT' : 'P07 · FOUND REPORT' }}</p><h1 class="page-title">{{ kind === 'LOST' ? '发布遗失线索' : '登记拾获物品' }}</h1><p class="page-lead">先提供可公开检索的信息，再补充仅用于核验的敏感特征。此页面不会把联系方式写进公开描述。</p></header>
    <div class="stepper" aria-label="发布步骤"><button v-for="entry in [{n:1,t:'基本信息'},{n:2,t:'时间地点'},{n:3,t:'隐私与确认'}]" :key="entry.n" :class="{ active: step >= entry.n }" type="button" @click="step = entry.n"><span>{{ entry.n }}</span>{{ entry.t }}</button></div>
    <form class="panel publish-form" @submit.prevent="save(true)">
      <section v-if="step === 1"><h2>描述这件物品</h2><div class="form-grid"><label class="wide"><span>标题</span><input v-model="form.title" required maxlength="120" placeholder="例如：黑色 Sony 入耳式耳机" /></label><label><span>类别</span><select v-model="form.category" required><option value="">请选择</option><option v-for="entry in categories" :key="entry.id" :value="entry.id">{{ entry.name }}</option></select></label><label><span>颜色</span><input v-model="form.color" placeholder="可填写多色，如：黑色,银色" /></label><label><span>品牌</span><input v-model="form.brand" placeholder="未知时请留空，不猜测" /></label><label class="wide"><span>公开描述</span><textarea v-model="form.description" required maxlength="3000" rows="7" placeholder="外观、材质、型号等可公开特征。不要填写手机号、完整证件号或私密核验答案。"></textarea><small>{{ form.description.length }}/3000</small></label></div></section>
      <section v-else-if="step === 2"><h2>事件发生在何时何地</h2><div class="form-grid"><label><span>{{ kind === 'LOST' ? '遗失时间' : '拾获时间' }}</span><input v-model="form.occurred_at" required type="datetime-local" /></label><label><span>公开地点</span><select v-model="form.location" required><option value="">请选择</option><option v-for="entry in locations" :key="entry.id" :value="entry.id">{{ entry.name }}</option></select></label><label v-if="kind === 'FOUND'" class="wide"><span>保管服务站</span><select v-model="form.station"><option value="">暂未送站</option><option v-for="entry in stations" :key="entry.id" :value="entry.id">{{ entry.name }} · {{ entry.status }}</option></select></label><label class="wide"><span>精确地点（受保护）</span><input v-model="form.location_detail" placeholder="例如：图书馆三楼东侧自习区，仅授权流程可见" /></label></div><div class="privacy-callout"><AppIcon name="map" /><div><strong>地点分层</strong><p>广场只显示公开区域；精确位置不会进入公共搜索结果或算法解释。</p></div></div></section>
      <section v-else><h2>提交前确认</h2><div class="review-card"><div><span>类型</span><strong>{{ kind === 'LOST' ? '遗失' : '招领' }}</strong></div><div><span>标题</span><strong>{{ form.title || '尚未填写' }}</strong></div><div><span>公开地点</span><strong>{{ form.location || '尚未选择' }}</strong></div><div><span>公开描述</span><strong>{{ form.description ? `${form.description.length} 字` : '尚未填写' }}</strong></div></div><label class="consent"><input required type="checkbox" />我确认公开内容不含联系方式、完整证件号、私密核验答案，并同意先经过内容审核。</label></section>
      <section v-if="step===2" style="margin-top:22px"><h3>地图标点（受保护，可选）</h3><AMapCampus pickable @pick="pickPoint"/><p v-if="point">已选择精确位置：{{point.longitude}}，{{point.latitude}}。公开页面不显示此标点。</p></section>
      <p v-if="error" class="form-message error">{{ error }}</p><p v-if="success" class="form-message success">{{ success }}</p>
      <footer><button v-if="step > 1" class="button button-ghost" type="button" @click="step--">上一步</button><button class="button button-ghost" type="button" :disabled="saving" @click="save(false)">保存草稿</button><button v-if="step < 3" class="button button-brand" type="button" @click="step++">下一步 <AppIcon name="arrow" /></button><button v-else class="button button-brand" type="submit" :disabled="saving">{{ saving ? '正在提交…' : '提交审核' }}</button></footer>
    </form>
  </div>
</template>

<style scoped>
.publish-page { max-width: 980px; }.stepper { display: grid; grid-template-columns: repeat(3,1fr); margin: 40px 0 18px; }.stepper button { display: flex; align-items: center; gap: 9px; padding: 14px 0; color: var(--ct-text-muted); border: 0; border-bottom: 2px solid var(--ct-border); background: transparent; cursor: pointer; }.stepper button.active { color: var(--ct-text); border-color: var(--ct-brand); }.stepper span { display: grid; place-items: center; width: 26px; aspect-ratio: 1; border: 1px solid currentColor; border-radius: 50%; font-size: 11px; }.publish-form { padding: 34px; }.publish-form h2 { margin: 0 0 26px; }.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }.form-grid .wide { grid-column: 1/-1; }.form-grid label span { display: block; margin-bottom: 8px; color: var(--ct-text-muted); font-size: 13px; }.form-grid input,.form-grid textarea,.form-grid select { width: 100%; padding: 13px 14px; color: var(--ct-text); border: 1px solid var(--ct-border); border-radius: 11px; outline: 0; background: var(--ct-bg-soft); }.form-grid input:focus,.form-grid textarea:focus,.form-grid select:focus { border-color: var(--ct-brand); }.form-grid small { display: block; margin-top: 6px; color: var(--ct-text-muted); text-align: right; }.privacy-callout { display: flex; gap: 14px; margin-top: 24px; padding: 18px; color: var(--ct-info); border: 1px solid rgba(98,180,255,.25); border-radius: 14px; background: rgba(98,180,255,.06); }.privacy-callout p { margin: 4px 0 0; color: var(--ct-text-muted); }.review-card { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; overflow: hidden; border: 1px solid var(--ct-border); border-radius: 14px; background: var(--ct-border); }.review-card div { display: flex; flex-direction: column; gap: 9px; padding: 18px; background: var(--ct-bg-soft); }.review-card span { color: var(--ct-text-muted); font-size: 12px; }.consent { display: flex; gap: 10px; margin: 24px 0; color: var(--ct-text-muted); line-height: 1.6; }.publish-form footer { display: flex; justify-content: flex-end; gap: 10px; margin-top: 30px; padding-top: 22px; border-top: 1px solid var(--ct-border); }.form-message { padding: 12px; border-radius: 10px; }.form-message.error { color: var(--ct-danger); background: rgba(255,111,120,.08); }.form-message.success { color: var(--ct-success); background: rgba(82,211,154,.08); }
@media (max-width: 620px) { .form-grid,.review-card { grid-template-columns: 1fr; }.form-grid .wide { grid-column: auto; }.publish-form { padding: 22px; }.stepper button { align-items: flex-start; flex-direction: column; } }
</style>
