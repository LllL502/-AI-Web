<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import AppIcon from '../../components/AppIcon.vue'
import ItemVisual from '../../components/ItemVisual.vue'
import { apiCached, ApiError } from '../../api/client'
import { itemCategoryIcon, rootItemCategories, type ItemCategory } from '../../utils/itemCategories'
interface Item { id: string; title: string; description: string; category_name: string; location_name: string; occurred_at: string; color: string; image_url?: string }
const router = useRouter()
const kind = ref<'FOUND' | 'LOST'>('FOUND')
const query = ref(''), category = ref(''), items = ref<Item[]>([]), loading = ref(true), error = ref('')
const metadataCategories = ref<ItemCategory[]>([])
const categories = computed(() => rootItemCategories(metadataCategories.value))
const visibleItems = computed(() => items.value.slice(0, 3))
const galleryTarget = computed(() => ({
  path: kind.value === 'FOUND' ? '/found' : '/lost',
  query: {
    ...(query.value.trim() ? { q: query.value.trim() } : {}),
    ...(category.value ? { category: category.value } : {}),
  },
}))
let requestVersion = 0
async function load() {
  const version = ++requestVersion
  loading.value = true; error.value = ''
  try {
    const params = new URLSearchParams({ kind: kind.value })
    if (category.value) params.set('category', category.value)
    const response = await apiCached<{ data: { items: Item[] } }>(`/items/?${params}`)
    if (version === requestVersion) items.value = response.data.items
  }
  catch (reason) { if (version === requestVersion) error.value = reason instanceof ApiError ? reason.message : '暂时无法加载物品，请稍后重试。' }
  finally { if (version === requestVersion) loading.value = false }
}
async function loadCategories() {
  try {
    const response = await apiCached<{ data: { categories: ItemCategory[] } }>('/items/metadata/')
    metadataCategories.value = response.data.categories
  } catch {
    // 物品列表仍可以使用；类别元数据失败时不回退到另一套硬编码字典。
    metadataCategories.value = []
  }
}
function search() { router.push(galleryTarget.value) }
function selectKind(value: 'FOUND' | 'LOST') { kind.value = value; category.value = '' }
function toggleCategory(id: number) { const value = String(id); category.value = category.value === value ? '' : value }
onMounted(loadCategories)
onBeforeUnmount(()=>{requestVersion++})
watch([kind, category], load, { immediate: true })
</script>
<template>
  <section class="home-hero" aria-labelledby="home-title">
    <div class="hero-inner">
      <div class="hero-copy">
        <span class="home-label">寻迹 · 让寻找有方向</span>
        <h1 id="home-title">你在找的，<br /><span>也许已有线索。</span></h1>
        <p class="hero-verse">一张照片，一句描述。<br />从校园里的点滴线索，找回你在意的那一件。</p>
        <div class="hero-actions"><RouterLink class="button button-brand" to="/assistant">开始 AI 寻物 <AppIcon name="arrow" /></RouterLink><RouterLink class="button button-ghost" to="/publish/found">我捡到了物品</RouterLink></div>
      </div>
      <div class="hero-art entry-board">
        <div class="board-heading"><span class="live-dot" aria-hidden="true"></span><span>校园里的新线索</span><AppIcon name="search" /></div>
        <div v-if="loading" class="preview-state">正在载入校园线索…</div>
        <div v-else-if="error" class="preview-state">暂时无法加载线索</div>
        <div v-else-if="!visibleItems.length" class="preview-state">新的线索，从你的分享开始。</div>
        <div v-else class="hero-previews">
          <RouterLink v-for="item in visibleItems.slice(0,2)" :key="item.id" :to="`/items/${item.id}`" class="preview-card">
            <ItemVisual :title="item.title" :category="item.category_name" :color="item.color" :image-url="item.image_url" />
            <div><span>{{ item.category_name }}</span><h2>{{ item.title }}</h2><p><AppIcon name="map" />{{ item.location_name }}</p></div>
            <AppIcon name="arrow" />
          </RouterLink>
        </div>
        <RouterLink class="board-more" :to="galleryTarget">浏览校园线索 <AppIcon name="arrow" /></RouterLink>
      </div>
    </div>
  </section>
  <section class="home-discovery" aria-label="查找校园物品">
    <div class="kind-switch" role="group" aria-label="信息类型"><button :class="{ active: kind === 'FOUND' }" :aria-pressed="kind === 'FOUND'" @click="selectKind('FOUND')">失物招领</button><button :class="{ active: kind === 'LOST' }" :aria-pressed="kind === 'LOST'" @click="selectKind('LOST')">寻物启事</button></div>
    <form class="home-search" @submit.prevent="search"><AppIcon name="search" /><input v-model="query" aria-label="搜索物品" placeholder="搜索物品名称、关键词或地点（如：校园卡、钥匙、图书馆…）" /><button type="submit" aria-label="提交搜索">搜索</button></form>
    <div class="category-row" role="group" aria-label="物品类别"><button v-for="entry in categories" :key="entry.id" :class="{ active: category === String(entry.id) }" :aria-pressed="category === String(entry.id)" @click="toggleCategory(entry.id)"><AppIcon :name="itemCategoryIcon(entry.code)" /><span>{{ entry.name }}</span></button></div>
    <div class="section-heading"><h2>留意身边的线索</h2><RouterLink :to="galleryTarget">查看全部 <AppIcon name="arrow" /></RouterLink></div>
    <p v-if="loading" class="home-state" role="status">正在整理校园里的最新线索…</p>
    <div v-else-if="error" class="home-state" role="alert"><p>{{ error }}</p><button class="button button-ghost" @click="load">重新加载</button></div>
    <div v-else-if="visibleItems.length" class="latest-grid">
      <RouterLink v-for="item in visibleItems" :key="item.id" :to="`/items/${item.id}`" class="latest-card">
        <ItemVisual :title="item.title" :category="item.category_name" :color="item.color" :image-url="item.image_url" />
        <div class="latest-body"><h3>{{ item.title }}</h3><span class="category-tag">{{ item.category_name }}</span><p>{{ item.description }}</p><div class="latest-meta"><span><AppIcon name="map" />{{ item.location_name }}</span><time>{{ new Date(item.occurred_at).toLocaleDateString('zh-CN') }}</time></div></div>
      </RouterLink>
    </div>
    <div v-else class="home-state"><AppIcon name="box" /><p>{{ category ? '这一类别暂时没有公开线索，试试其他类别。' : '暂时没有公开物品，发布一条线索，让找回从这里开始。' }}</p><RouterLink class="button button-brand" :to="kind === 'FOUND' ? '/publish/found' : '/publish/lost'">发布线索</RouterLink></div>
  </section>
</template>
<style scoped>
.home-hero { position: relative; overflow: hidden; }
.hero-inner { display: grid; grid-template-columns: minmax(0,.76fr) minmax(0,1.24fr); align-items: center; width: min(1360px,calc(100% - 80px)); margin: 0 auto; min-height: 490px; }
.hero-copy { position: relative; align-self: stretch; display: flex; flex-direction: column; justify-content: center; padding: 30px 12px 100px 24px; min-width: 0; }
.hero-copy h1 { position: relative; z-index: 1; margin: 0 0 20px; font: 800 clamp(52px,5.6vw,82px)/1.17 'Songti SC','SimSun',serif; letter-spacing: .01em; color: var(--ct-brand); }
.hero-copy h1 span { color: var(--ct-info); }
.hero-verse { z-index: 1; margin: 0; font: 18px/1.8 'Songti SC','SimSun',serif; color: var(--ct-text); }
.hero-actions { position: relative; z-index: 1; display: flex; flex-wrap: wrap; gap: 16px; margin-top: 24px; }
.hero-actions .button { min-height: 44px; min-width: 162px; border-radius: 15px; font-family: 'Songti SC','SimSun',serif; }
.hero-actions .button-ghost { border-color: var(--ct-brand); color: var(--ct-brand); background: rgba(255,253,248,.5); }
.paper-plane { position: absolute; width: 145px; right: 8px; top: 66px; fill: none; stroke: var(--ct-brand); stroke-width: 1.25; }
.hero-campus { position: absolute; left: -20px; bottom: 23px; width: calc(100% + 18px); color: #9c927b; opacity: .42; }
.hero-art { min-width: 0; padding: 18px 10px 24px 20px; overflow: hidden; }
.hero-art img { display: block; width: 100%; height: auto; max-height: 475px; object-fit: contain; }
.home-discovery { position: relative; width: min(1360px,calc(100% - 80px)); margin: 0 auto; padding-bottom: 24px; }
.kind-switch { position: relative; display: flex; width: min(410px,100%); margin: -12px auto 14px; padding: 5px; background: rgba(248,244,236,.94); border: 1px solid var(--ct-border); border-radius: 30px; }
.kind-switch button { width: 50%; padding: 10px; background: transparent; color: var(--ct-text); border: 0; border-radius: 24px; cursor: pointer; font-family: 'Songti SC','SimSun',serif; }
.kind-switch .active { background: var(--ct-brand); color: var(--ct-brand-ink); }
.home-search { display: flex; align-items: center; gap: 13px; max-width: 970px; min-height: 46px; margin: auto; padding-left: 20px; background: rgba(255,253,248,.8); border: 1px solid var(--ct-border); border-radius: 14px; overflow: hidden; }
.home-search > svg { color: var(--ct-text); font-size: 20px; flex-shrink: 0; }
.home-search input { width: 0; min-width: 0; flex: 1; padding: 13px 0; border: 0; background: transparent; color: var(--ct-text); font-size: 13px; }
.home-search button { align-self: stretch; min-width: 104px; padding: 0 18px; color: var(--ct-brand-ink); background: var(--ct-brand); border: 0; font-family: 'Songti SC','SimSun',serif; cursor: pointer; }
.category-row { display: grid; grid-template-columns: repeat(5,minmax(0,1fr)); gap: 22px; margin: 18px auto 21px; max-width: 1220px; }
.category-row button { display: grid; place-items: center; gap: 11px; min-height: 94px; padding: 12px; color: var(--ct-text); border: 1px solid rgba(222,212,197,.4); border-radius: 14px; background: rgba(255,253,248,.55); box-shadow: 0 3px 12px rgba(70,48,28,.03); cursor: pointer; font: 15px 'Songti SC','SimSun',serif; }
.category-row svg { font-size: 31px; color: var(--ct-info); }
.category-row button:nth-child(even) svg { color: var(--ct-brand); }
.category-row .active { border-color: var(--ct-border-strong); background: #eee2d6; color: var(--ct-brand); }
.section-heading { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 12px; }
.section-heading h2 { position: relative; margin: 0; padding-left: 17px; font: 700 21px/1.4 'Songti SC','SimSun',serif; }
.section-heading h2::before { content: ''; position: absolute; left: 0; top: 4px; width: 4px; height: 22px; background: var(--ct-brand); border-radius: 2px; }
.section-heading > a { display: inline-flex; align-items: center; gap: 10px; color: var(--ct-text-muted); font-size: 13px; }
.latest-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 14px; }
.latest-card { display: flex; align-items: stretch; gap: 14px; padding: 12px; min-width: 0; overflow: hidden; background: rgba(255,253,248,.84); border: 1px solid var(--ct-border); border-radius: 12px; box-shadow: 0 3px 15px rgba(70,48,28,.04); transition: transform .15s,border-color .15s; }
.latest-card:hover { transform: translateY(-2px); border-color: var(--ct-border-strong); }
.latest-body { min-width: 0; display: flex; align-items: start; flex-direction: column; }
.latest-body h3 { margin: 0 0 6px; font: 700 18px/1.4 'Songti SC','SimSun',serif; }
.latest-body p { margin: 7px 0 9px; color: var(--ct-text-muted); font-size: 12px; line-height: 1.7; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.category-tag { padding: 3px 7px; border-radius: 5px; background: #f0e0d8; color: var(--ct-brand); font-size: 10px; }
.latest-meta { display: flex; flex-wrap: wrap; gap: 6px 11px; margin-top: auto; color: var(--ct-text-muted); font-size: 10px; }
.latest-meta span { display: inline-flex; align-items: center; gap: 4px; }
.latest-meta svg { color: var(--ct-brand); }
.home-state { display: grid; place-items: center; align-content: center; min-height: 160px; padding: 25px; border: 1px dashed var(--ct-border); border-radius: 12px; text-align: center; color: var(--ct-text-muted); }
.home-state > svg { font-size: 34px; }
.home-state p { line-height: 1.8; }
@media(max-width:1100px) { .hero-inner,.home-discovery { width: calc(100% - 48px); }.hero-copy { padding-left: 0; }.hero-copy h1 { font-size: 62px; }.hero-verse { font-size: 15px; }.paper-plane { width: 120px; top: 80px; }.hero-actions { gap: 10px; }.hero-actions .button { min-width: 135px; padding-inline: 12px; }.latest-grid { grid-template-columns: repeat(2,minmax(0,1fr)); }.latest-card:last-child { grid-column: 1/-1; }.category-row { gap: 12px; } }
@media(max-width:760px) { .hero-inner { grid-template-columns: 1fr; min-height: auto; }.hero-copy { padding: 28px 0 75px; }.hero-copy h1 { font-size: 54px; }.hero-copy h1 br { display: none; }.hero-copy h1 span { margin-right: .15em; }.hero-verse { font-size: 16px; }.paper-plane { top: 30px; right: 0; width: 95px; }.hero-campus { bottom: 0; width: 95%; left: 0; max-height: 85px; }.hero-art { padding: 8px 10px 30px; }.hero-art img { max-height: 320px; }.kind-switch { margin-top: -6px; }.latest-grid { grid-template-columns: 1fr; }.latest-card:last-child { grid-column: auto; } }
@media(max-width:480px) { .hero-inner,.home-discovery { width: calc(100% - 28px); }.hero-copy h1 { font-size: 44px; }.hero-copy { padding-top: 24px; }.paper-plane { top: 68px; width: 76px; }.hero-verse { font-size: 14px; }.hero-actions .button { min-width: 140px; font-size: 13px; }.category-row { gap: 6px; }.category-row button { padding: 12px 2px; font-size: 11px; min-height: 80px; border-radius: 9px; }.category-row svg { font-size: 25px; }.home-search { padding-left: 10px; gap: 8px; }.home-search button { min-width: 62px; padding-inline: 12px; }.home-search input { font-size: 11px; }.latest-card { gap: 12px; }.latest-body h3 { font-size: 17px; } }
</style>
