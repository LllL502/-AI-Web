<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { apiCached, ApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'
import ItemVisual from '../../components/ItemVisual.vue'
import { rootItemCategories, type ItemCategory } from '../../utils/itemCategories'

const props = defineProps<{ kind: 'LOST' | 'FOUND' }>()
interface ItemCard { id: string; title: string; description: string; category_name: string; location_name: string; occurred_at: string; brand: string; color: string; business_status: string; image_url?: string }
interface CampusLocation { id: number; name: string; code: string; parent_id: number | null }
const items = ref<ItemCard[]>([])
const route = useRoute()
const router = useRouter()
const query = ref('')
const category = ref('')
const location = ref('')
const days = ref('')
const metadataCategories = ref<ItemCategory[]>([])
const metadataLocations = ref<CampusLocation[]>([])
const categoryOptions = computed(() => rootItemCategories(metadataCategories.value))
const locationOptions = computed(() => metadataLocations.value.filter((entry) => entry.parent_id !== null))
const loading = ref(true)
const error = ref('')
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const selectedCategoryName = computed(() => categoryOptions.value.find((entry) => String(entry.id) === category.value)?.name ?? '')
const title = computed(() => props.kind === 'LOST' ? '遗失广场' : '招领广场')
const subtitle = computed(() => props.kind === 'LOST' ? '正在寻找的物品' : '等待主人核验的物品')

function routeValue(name: string): string {
  const value = route.query[name]
  return typeof value === 'string' ? value : ''
}

function syncFiltersFromRoute() {
  query.value = routeValue('q')
  category.value = routeValue('category')
  location.value = routeValue('location')
  days.value = routeValue('days')
  const requestedPage = Number.parseInt(routeValue('page'), 10)
  page.value = Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1
}

let requestVersion = 0
async function load() {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ kind: props.kind })
    if (query.value.trim()) params.set('q', query.value.trim())
    if (category.value) params.set('category', category.value)
    if (location.value) params.set('location', location.value)
    if (days.value) params.set('days', days.value)
    params.set('page', String(page.value))
    const response = await apiCached<{ data: { items: ItemCard[]; total: number; page: number; page_size: number } }>(`/items/?${params}`)
    if (version === requestVersion) {
      items.value = response.data.items
      total.value = response.data.total
      page.value = response.data.page
      pageSize.value = response.data.page_size
    }
  } catch (reason) {
    if (version === requestVersion) error.value = reason instanceof ApiError ? reason.message : '暂时无法加载线索，请确认后端服务已启动。'
  } finally { if (version === requestVersion) loading.value = false }
}

async function loadMetadata() {
  try {
    const response = await apiCached<{ data: { categories: ItemCategory[]; locations: CampusLocation[] } }>('/items/metadata/')
    metadataCategories.value = response.data.categories
    metadataLocations.value = response.data.locations
  } catch {
    metadataCategories.value = []
    metadataLocations.value = []
  }
}

function filterQuery(targetPage = 1) {
  return {
    ...(query.value.trim() ? { q: query.value.trim() } : {}),
    ...(category.value ? { category: category.value } : {}),
    ...(location.value ? { location: location.value } : {}),
    ...(days.value ? { days: days.value } : {}),
    ...(targetPage > 1 ? { page: String(targetPage) } : {}),
  }
}

async function applyFilters() {
  const nextQuery = filterQuery(1)
  const before = route.fullPath
  await router.replace({ path: route.path, query: nextQuery })
  if (route.fullPath === before) await load()
}

async function goToPage(targetPage: number) {
  if (targetPage < 1 || targetPage > pages.value || targetPage === page.value) return
  await router.push({ path: route.path, query: filterQuery(targetPage) })
}

onMounted(loadMetadata)
watch(
  () => [props.kind, route.query.q, route.query.category, route.query.location, route.query.days, route.query.page],
  () => { syncFiltersFromRoute(); void load() },
  { immediate: true },
)
</script>

<template>
  <div class="page">
    <header class="gallery-header">
      <div><h1 class="page-title">{{ title }}</h1><p class="page-lead">在熟悉的校园里，为遗失的物品留下一条回来的路。这里只展示审核通过的公开线索。</p></div>
      <RouterLink class="button button-brand" :to="kind === 'LOST' ? '/publish/lost' : '/publish/found'"><AppIcon name="plus" />{{ kind === 'LOST' ? '发布遗失' : '登记拾获' }}</RouterLink>
    </header>
    <form class="filter-panel panel" @submit.prevent="applyFilters"><label><span>搜索{{ subtitle }}</span><div class="search-box"><AppIcon name="search" /><input v-model="query" :placeholder="kind === 'LOST' ? '例如：黑色耳机 图书馆' : '例如：校园卡 体育馆'" /><button type="submit">搜索</button></div></label><div class="filters"><select v-model="category" aria-label="物品类别" @change="applyFilters"><option value="">全部类别</option><option v-for="entry in categoryOptions" :key="entry.id" :value="String(entry.id)">{{ entry.name }}</option></select><select v-model="location" aria-label="校园区域" @change="applyFilters"><option value="">全部区域</option><option v-for="entry in locationOptions" :key="entry.id" :value="String(entry.id)">{{ entry.name }}</option></select><select v-model="days" aria-label="时间范围" @change="applyFilters"><option value="">全部时间</option><option value="7">近 7 天</option><option value="30">近 30 天</option></select></div></form>
    <p v-if="loading" class="state-panel">正在从后端读取公开线索…</p>
    <p v-else-if="error" class="state-panel error">{{ error }}</p>
    <template v-else-if="items.length">
      <div class="results-summary"><span>共 <strong>{{ total }}</strong> 条公开线索<span v-if="selectedCategoryName">，当前类别：{{ selectedCategoryName }}</span></span><span>第 {{ page }} / {{ pages }} 页</span></div>
      <div class="item-grid">
        <RouterLink v-for="item in items" :key="item.id" :to="`/items/${item.id}`" class="item-card">
          <div class="item-visual"><ItemVisual :title="item.title" :category="item.category_name" :color="item.color" :image-url="item.image_url" variant="gallery" /><span class="status-tag">{{ item.business_status }}</span></div>
          <div class="item-body"><div class="item-meta"><span>{{ item.category_name }}</span><span>{{ new Date(item.occurred_at).toLocaleDateString('zh-CN') }}</span></div><h2>{{ item.title }}</h2><p>{{ item.description }}</p><footer><span><AppIcon name="map" />{{ item.location_name }}</span><span>{{ [item.color, item.brand].filter(Boolean).join(' · ') || '特征待补充' }}</span></footer></div>
        </RouterLink>
      </div>
      <nav v-if="pages > 1" class="gallery-pagination" aria-label="物品列表分页"><button :disabled="page <= 1" @click="goToPage(page - 1)">上一页</button><span>{{ page }} / {{ pages }}</span><button :disabled="page >= pages" @click="goToPage(page + 1)">下一页</button></nav>
    </template>
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
.results-summary { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin: -10px 0 16px; color: var(--ct-text-muted); font-size: 12px; }
.results-summary strong { color: var(--ct-brand); font-size: 17px; }
.item-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }
.item-card { overflow: hidden; border: 1px solid var(--ct-border); border-radius: var(--ct-radius-md); background: var(--ct-surface); transition: transform .18s ease, border-color .18s ease; }
.item-card:hover { transform: translateY(-4px); border-color: var(--ct-border-strong); }
.item-visual { position: relative; }.item-visual .status-tag { position: absolute; top: 12px; right: 12px; background: var(--ct-surface); color: var(--ct-text-muted); font-size: 10px; }
.item-body { padding: 20px; }
.item-meta, .item-body footer { display: flex; justify-content: space-between; gap: 12px; color: var(--ct-text-muted); font-size: 11px; }
.item-body h2 { margin: 12px 0 9px; font-size: 19px; }
.item-body p { display: -webkit-box; min-height: 3.3em; overflow: hidden; color: var(--ct-text-muted); line-height: 1.65; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.item-body footer { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--ct-border); }
.item-body footer span { display: flex; align-items: center; gap: 5px; }
.state-panel { display: grid; place-items: center; min-height: 270px; padding: 36px; color: var(--ct-text-muted); border: 1px dashed var(--ct-border); border-radius: var(--ct-radius-lg); text-align: center; }
.state-panel.error { color: var(--ct-danger); }
.gallery-pagination { display: flex; justify-content: center; align-items: center; gap: 20px; margin: 28px 0 8px; }
.gallery-pagination button { min-width: 92px; padding: 10px 16px; color: var(--ct-text); border: 1px solid var(--ct-border); border-radius: 10px; background: var(--ct-surface); cursor: pointer; }
.gallery-pagination button:disabled { cursor: not-allowed; opacity: .42; }
.gallery-pagination span { color: var(--ct-text-muted); font-size: 12px; }
@media (max-width: 980px) { .filter-panel { grid-template-columns: 1fr; } .item-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 660px) { .gallery-header { align-items: start; flex-direction: column; } .search-box { min-width: 0; } .filters { align-items: stretch; flex-direction: column; } .item-grid { grid-template-columns: 1fr; } }
</style>
