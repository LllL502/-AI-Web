<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'

const props = defineProps<{ kind: 'LOST' | 'FOUND' }>()
interface ItemCard { id: string; title: string; description: string; category_name: string; location_name: string; occurred_at: string; brand: string; color: string; business_status: string }
const items = ref<ItemCard[]>([])
const query = ref('')
const loading = ref(true)
const error = ref('')
const title = computed(() => props.kind === 'LOST' ? '遗失广场' : '招领广场')
const subtitle = computed(() => props.kind === 'LOST' ? '正在寻找的物品' : '等待主人核验的物品')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ kind: props.kind })
    if (query.value.trim()) params.set('q', query.value.trim())
    const response = await api<{ data: { items: ItemCard[] } }>(`/items/?${params}`)
    items.value = response.data.items
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '暂时无法加载线索，请确认后端服务已启动。'
  } finally { loading.value = false }
}
onMounted(load)
watch(() => props.kind, load)
</script>

<template>
  <div class="page">
    <header class="gallery-header">
      <div><p class="eyebrow">{{ kind === 'LOST' ? 'LOST ITEMS' : 'FOUND ITEMS' }}</p><h1 class="page-title">{{ title }}</h1><p class="page-lead">仅展示审核通过的公开信息。精确地点、联系方式和核验答案不会出现在列表中。</p></div>
      <RouterLink class="button button-brand" :to="kind === 'LOST' ? '/publish/lost' : '/publish/found'"><AppIcon name="plus" />{{ kind === 'LOST' ? '发布遗失' : '登记拾获' }}</RouterLink>
    </header>
    <form class="filter-panel panel" @submit.prevent="load"><label><span>搜索{{ subtitle }}</span><div class="search-box"><AppIcon name="search" /><input v-model="query" :placeholder="kind === 'LOST' ? '例如：黑色耳机 图书馆' : '例如：校园卡 体育馆'" /><button type="submit">搜索</button></div></label><div class="filters"><select aria-label="物品类别"><option>全部类别</option><option>数码设备</option><option>证件卡片</option><option>学习用品</option></select><select aria-label="校园区域"><option>全部区域</option><option>图书馆</option><option>教学楼</option><option>宿舍区</option></select><select aria-label="时间范围"><option>近 7 天</option><option>近 30 天</option><option>全部时间</option></select></div></form>
    <p v-if="loading" class="state-panel">正在从后端读取公开线索…</p>
    <p v-else-if="error" class="state-panel error">{{ error }}</p>
    <div v-else-if="items.length" class="item-grid">
      <RouterLink v-for="item in items" :key="item.id" :to="`/items/${item.id}`" class="item-card">
        <div class="item-visual"><AppIcon name="box" /><span class="status-tag">{{ item.business_status }}</span></div>
        <div class="item-body"><div class="item-meta"><span>{{ item.category_name }}</span><span>{{ new Date(item.occurred_at).toLocaleDateString('zh-CN') }}</span></div><h2>{{ item.title }}</h2><p>{{ item.description }}</p><footer><span><AppIcon name="map" />{{ item.location_name }}</span><span>{{ [item.color, item.brand].filter(Boolean).join(' · ') || '特征待补充' }}</span></footer></div>
      </RouterLink>
    </div>
    <div v-else class="state-panel"><AppIcon name="search" /><h2>没有符合条件的公开线索</h2><p>调整筛选条件，或发布一条更完整的信息以便后续匹配。</p></div>
  </div>
</template>

<style scoped>
.gallery-header { display: flex; align-items: end; justify-content: space-between; gap: 24px; }
.filter-panel { display: grid; grid-template-columns: 1fr auto; gap: 22px; margin: 36px 0 28px; padding: 20px; box-shadow: none; }
.filter-panel label > span { display: block; margin-bottom: 8px; color: var(--ct-text-muted); font-size: 12px; }
.search-box { display: flex; align-items: center; gap: 10px; min-width: 360px; padding-left: 13px; border: 1px solid var(--ct-border); border-radius: 12px; background: var(--ct-bg-soft); }
.search-box input { flex: 1; min-width: 0; padding: 12px 0; color: var(--ct-text); border: 0; outline: 0; background: transparent; }
.search-box button { align-self: stretch; padding: 0 18px; color: var(--ct-brand-ink); border: 0; border-radius: 10px; background: var(--ct-brand); cursor: pointer; }
.filters { display: flex; align-items: end; gap: 8px; }
.filters select { padding: 12px; color: var(--ct-text); border: 1px solid var(--ct-border); border-radius: 10px; background: var(--ct-bg-soft); }
.item-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }
.item-card { overflow: hidden; border: 1px solid var(--ct-border); border-radius: var(--ct-radius-md); background: var(--ct-surface); transition: transform .18s ease, border-color .18s ease; }
.item-card:hover { transform: translateY(-4px); border-color: var(--ct-border-strong); }
.item-visual { display: flex; justify-content: space-between; align-items: start; min-height: 160px; padding: 18px; color: var(--ct-brand); background: radial-gradient(circle at 50% 40%, rgba(98,180,255,.2), transparent 50%), linear-gradient(145deg,#152d47,#091522); font-size: 54px; }
.item-visual .status-tag { color: var(--ct-text-muted); font-size: 10px; }
.item-body { padding: 20px; }
.item-meta, .item-body footer { display: flex; justify-content: space-between; gap: 12px; color: var(--ct-text-muted); font-size: 11px; }
.item-body h2 { margin: 12px 0 9px; font-size: 19px; }
.item-body p { display: -webkit-box; min-height: 3.3em; overflow: hidden; color: var(--ct-text-muted); line-height: 1.65; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.item-body footer { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--ct-border); }
.item-body footer span { display: flex; align-items: center; gap: 5px; }
.state-panel { display: grid; place-items: center; min-height: 270px; padding: 36px; color: var(--ct-text-muted); border: 1px dashed var(--ct-border); border-radius: var(--ct-radius-lg); text-align: center; }
.state-panel.error { color: var(--ct-danger); }
@media (max-width: 980px) { .filter-panel { grid-template-columns: 1fr; } .item-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 660px) { .gallery-header { align-items: start; flex-direction: column; } .search-box { min-width: 0; } .filters { align-items: stretch; flex-direction: column; } .item-grid { grid-template-columns: 1fr; } }
</style>
