<script setup lang="ts">
import {readableApiError} from '../../api/client'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import AppIcon from '../../components/AppIcon.vue'
import AssistantCompanion from '../../components/AssistantCompanion.vue'
import ItemVisual from '../../components/ItemVisual.vue'
import { apiCached, ApiError } from '../../api/client'
import { itemCategoryIcon, rootItemCategories, type ItemCategory } from '../../utils/itemCategories'
import { queueAssistantImage } from '../../stores/assistantDraft'

type Kind = 'FOUND' | 'LOST'
type KindFilter = 'ALL' | Kind
interface Item {
 is_demo?:boolean;image_note?:string;
  id: string
  title: string
  description: string
  kind: Kind
  category_name: string
  location_name: string
  occurred_at: string
  color: string
  image_url?: string
  business_status?: string
}

const router = useRouter()
const query = ref('')
const category = ref('')
const kindFilter = ref<KindFilter>('ALL')
const items = ref<Item[]>([])
const loading = ref(true)
const error = ref('')
const metadataCategories = ref<ItemCategory[]>([])
const categories = computed(() => rootItemCategories(metadataCategories.value))
const visibleItems = computed(() => {
  const filtered = kindFilter.value === 'ALL'
    ? items.value
    : items.value.filter(item => item.kind === kindFilter.value)
  return filtered.slice(0, 3)
})
const heroItems = computed(() => {const featured:Item[]=[];const categories=new Set<string>();for(const item of items.value){if(item.image_url&&!categories.has(item.category_name)){featured.push(item);categories.add(item.category_name);if(featured.length===4)break}}return [...featured,...items.value.filter(item=>item.image_url&&!featured.includes(item)),...items.value.filter(item=>!item.image_url)].slice(0,4)})
const previewItems = computed(() => heroItems.value.slice(0, 2))
const searchTarget = computed(() => ({
  path: '/search',
  query: {
    ...(query.value.trim() ? { q: query.value.trim() } : {}),
    ...(category.value ? { category: category.value } : {}),
    ...(kindFilter.value !== 'ALL' ? { kind: kindFilter.value } : {}),
  },
}))

let requestVersion = 0
async function load() {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  const categoryQuery = category.value ? `&category=${encodeURIComponent(category.value)}` : ''
  const [foundResult, lostResult] = await Promise.allSettled([
    apiCached<{ data: { items: Item[] } }>(`/items/?kind=FOUND${categoryQuery}`),
    apiCached<{ data: { items: Item[] } }>(`/items/?kind=LOST${categoryQuery}`),
  ])
  if (version !== requestVersion) return

  const foundItems = foundResult.status === 'fulfilled'
    ? foundResult.value.data.items.map(item => ({ ...item, kind: 'FOUND' as const }))
    : []
  const lostItems = lostResult.status === 'fulfilled'
    ? lostResult.value.data.items.map(item => ({ ...item, kind: 'LOST' as const }))
    : []

  if (foundResult.status === 'rejected' && lostResult.status === 'rejected') {
    const reason = foundResult.reason ?? lostResult.reason
    error.value = readableApiError(reason,'暂时无法加载校园线索，请稍后重试。')
    items.value = []
  } else {
    const unique = new Map<string, Item>()
    for (const item of [...foundItems, ...lostItems]) unique.set(item.id, item)
    items.value = [...unique.values()].sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at))
    if (foundResult.status === 'rejected' || lostResult.status === 'rejected') {
      error.value = '部分线索暂时无法加载，当前仍可浏览已获取的公开记录。'
    }
  }
  loading.value = false
}

async function loadCategories() {
  try {
    const response = await apiCached<{ data: { categories: ItemCategory[] } }>('/items/metadata/')
    metadataCategories.value = response.data.categories
  } catch {
    metadataCategories.value = []
  }
}

function search() {
  void router.push(searchTarget.value)
}

function toggleCategory(id: number) {
  category.value = category.value === String(id) ? '' : String(id)
}

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间待核实'
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function relativeTime(value: string) {
  const timestamp = Date.parse(value)
  if (Number.isNaN(timestamp)) return '时间待核实'
  const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60_000))
  if (minutes < 1) return '刚刚发布'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  if (hours < 48) return '昨天'
  return formatDate(value)
}

function kindLabel(kind: Kind) {
  return kind === 'LOST' ? '寻物启事' : '失物招领'
}

function categoryHint(code: string) {
  if (/electronic|digital|device/i.test(code)) return '耳机 / 充电宝 / U 盘'
  if (/card|document|identity/i.test(code)) return '校园卡 / 身份证 / 学生证'
  if (/key/i.test(code)) return '钥匙 / 门禁卡 / 车钥匙'
  if (/book|study/i.test(code)) return '教材 / 笔记 / 资料等'
  if (/drink|daily|life/i.test(code)) return '水杯 / 雨伞 / 生活用品'
  return '校园里的常见物品'
}

const aiMode = ref<'text' | 'image'>('text')
const aiKind = ref<Kind>('LOST')
const aiDescription = ref('')
const aiImage = ref<File | null>(null)
const aiImagePreview = ref('')
const aiError = ref('')

function onAiImageChange(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] ?? null
  aiImage.value = file
  aiError.value = ''
  if (aiImagePreview.value) URL.revokeObjectURL(aiImagePreview.value)
  aiImagePreview.value = file && typeof URL.createObjectURL === 'function' ? URL.createObjectURL(file) : ''
}

function startAiSearch() {
  const description = aiDescription.value.trim()
  if (aiMode.value === 'text' && description.length < 5) {
    aiError.value = '请至少输入 5 个字，描述你丢失或拾到的物品。'
    return
  }
  if (aiMode.value === 'image' && !aiImage.value) {
    aiError.value = '请先选择一张物品照片。'
    return
  }
  const image = aiMode.value === 'image' ? aiImage.value : null
  if (image && image.size > 8 * 1024 * 1024) {
    aiError.value = '图片不能超过 8MB，请重新选择。'
    return
  }
  if (image) queueAssistantImage(image)
  void router.push({
    path: '/assistant',
    query: {
      kind: aiKind.value,
      ...(description ? { description } : {}),
      ...(image ? { startWithImage: '1' } : {}),
    },
  })
}

onMounted(() => {
  void loadCategories()
})
onBeforeUnmount(() => {
  requestVersion++
  if (aiImagePreview.value) URL.revokeObjectURL(aiImagePreview.value)
})
watch(category, () => { void load() }, { immediate: true })
</script>

<template>
  <div class="home-page">
    <section class="home-hero" aria-labelledby="home-title">
      <div class="hero-inner">
        <div class="hero-copy">
          <p class="home-label">寻迹 · 属于我们校园的智能失物招领平台</p>
          <h1 id="home-title">一张照片，一句描述，<br />帮你<span>找到线索</span></h1>
          <p class="hero-verse">让遗失的物品更快回到主人手中</p>
          <form class="hero-search" @submit.prevent="search">
            <AppIcon name="search" />
            <input v-model="query" aria-label="搜索校园物品" placeholder="试试搜索：如“学生卡”“黑色耳机”“图书馆丢失的水杯”" />
            <button type="submit">搜索</button>
          </form>
          <div class="hero-actions">
            <RouterLink class="button button-brand" to="/assistant"><AppIcon name="spark" />开始 AI 寻物 <AppIcon name="arrow" /></RouterLink>
            <RouterLink class="button button-publish" to="/publish/lost"><AppIcon name="plus" />发布线索 <AppIcon name="arrow" /></RouterLink>
          </div>
          <div class="hero-trust" aria-label="平台服务特点">
            <span><i>✓</i> AI 智能匹配</span>
            <span><i>✓</i> 按校区查找线索</span>
            <span><i>✓</i> 快速找回遗失物品</span>
          </div>
        </div>

        <aside class="hero-board" aria-label="校园里的线索">
          <div class="board-heading">
            <span class="board-icon"><AppIcon name="bell" /></span>
            <h2>校园里的线索</h2>
            <RouterLink to="/search">查看更多 <AppIcon name="arrow" /></RouterLink>
          </div>
          <p v-if="loading" class="board-state">正在载入校园线索…</p>
          <p v-else-if="!heroItems.length" class="board-state">新的线索，从你的分享开始。</p>
          <div v-else class="hero-previews">
            <RouterLink v-for="item in heroItems" :key="item.id" :to="`/items/${item.id}`" class="preview-card">
              <ItemVisual :is-demo="item.is_demo" :image-note="item.image_note" :title="item.title" :category="item.category_name" :color="item.color" :image-url="item.image_url" />
              <div class="preview-info">
                <h3>{{ item.title }}</h3>
                <p><AppIcon name="map" />{{ item.location_name || '地点待核实' }}</p>
                <time>{{ relativeTime(item.occurred_at) }}</time>
              </div>
              <span class="kind-pill" :class="item.kind === 'LOST' ? 'is-lost' : 'is-found'">{{ kindLabel(item.kind) }}</span>
            </RouterLink>
          </div>
        </aside>
      </div>
    </section>

    <section class="home-content" aria-label="校园失物招领内容">
      <section class="category-section" aria-labelledby="category-title">
        <div class="section-heading">
          <h2 id="category-title">按类别快速查找</h2>
          <RouterLink to="/search">全部分类 <AppIcon name="arrow" /></RouterLink>
        </div>
        <div class="category-row" role="group" aria-label="物品类别">
          <button
            v-for="entry in categories"
            :key="entry.id"
            :class="{ active: category === String(entry.id) }"
            :aria-pressed="category === String(entry.id)"
            @click="toggleCategory(entry.id)"
          >
            <span class="category-icon"><AppIcon :name="itemCategoryIcon(entry.code)" /></span>
            <span class="category-copy"><strong>{{ entry.name }}</strong><small>{{ categoryHint(entry.code) }}</small></span>
          </button>
        </div>
      </section>

      <section class="latest-section" aria-labelledby="latest-title">
        <div class="section-heading latest-heading">
          <h2 id="latest-title"><span class="heading-icon"><AppIcon name="search" /></span>最新线索</h2>
          <div class="latest-actions">
            <div class="latest-tabs" role="group" aria-label="筛选线索类型">
              <button :class="{ active: kindFilter === 'ALL' }" :aria-pressed="kindFilter === 'ALL'" @click="kindFilter = 'ALL'">全部</button>
              <button :class="{ active: kindFilter === 'LOST' }" :aria-pressed="kindFilter === 'LOST'" @click="kindFilter = 'LOST'">寻物启事</button>
              <button :class="{ active: kindFilter === 'FOUND' }" :aria-pressed="kindFilter === 'FOUND'" @click="kindFilter = 'FOUND'">失物招领</button>
            </div>
            <RouterLink to="/search">查看更多 <AppIcon name="arrow" /></RouterLink>
          </div>
        </div>

        <p v-if="loading" class="home-state" role="status">正在整理校园里的最新线索…</p>
        <div v-else-if="error && !items.length" class="home-state" role="alert">
          <p>{{ error }}</p><button class="button button-ghost" @click="load">重新加载</button>
        </div>
        <div v-else-if="visibleItems.length" class="latest-grid">
          <RouterLink v-for="item in visibleItems" :key="item.id" :to="`/items/${item.id}`" class="latest-card">
            <ItemVisual :is-demo="item.is_demo" :image-note="item.image_note" :title="item.title" :category="item.category_name" :color="item.color" :image-url="item.image_url" />
            <div class="latest-body">
              <div class="latest-title-row"><h3>{{ item.title }}</h3><span class="kind-pill" :class="item.kind === 'LOST' ? 'is-lost' : 'is-found'">{{ kindLabel(item.kind) }}</span></div>
              <p>{{ item.description || '暂无更多描述，请打开线索查看详情。' }}</p>
              <div class="latest-meta">
                <span><AppIcon name="map" />{{ item.location_name || '地点待核实' }}</span>
                <time><AppIcon name="search" />{{ formatDate(item.occurred_at) }}</time>
              </div>
            </div>
          </RouterLink>
        </div>
        <div v-else class="home-state">
          <AppIcon name="box" />
          <p>{{ category ? '这一类别暂时没有公开线索，试试其他类别。' : kindFilter !== 'ALL' ? '当前类型暂时没有公开线索，切换到“全部”看看吧。' : '暂时没有公开物品，发布一条线索，让找回从这里开始。' }}</p>
          <RouterLink class="button button-brand" to="/publish/lost">发布线索</RouterLink>
        </div>
        <p v-if="error && items.length" class="partial-error" role="status">{{ error }}</p>
      </section>

      <section class="ai-workspace" aria-labelledby="ai-title">
        <div class="ai-heading">
          <div><h2 id="ai-title">AI 寻物工作台</h2><p>上传物品照片或描述特征，AI 提取关键信息后，帮你快速匹配可能的线索</p></div>
          <span class="ai-heading-note"><AppIcon name="shield" /> 先确认信息，再检索公开线索</span>
        </div>
        <AssistantCompanion :mode="aiMode" :description="aiDescription" :kind="aiKind" @apply="aiDescription = $event; aiMode = 'text'" @continue="startAiSearch" />
        <div class="ai-workspace-grid">
          <section class="ai-input-card" aria-label="描述或上传物品">
            <div class="ai-tabs" role="tablist" aria-label="输入方式">
              <button role="tab" :aria-selected="aiMode === 'text'" :class="{ active: aiMode === 'text' }" @click="aiMode = 'text'"><AppIcon name="plus" />文字描述</button>
              <button role="tab" :aria-selected="aiMode === 'image'" :class="{ active: aiMode === 'image' }" @click="aiMode = 'image'"><AppIcon name="card" />上传照片</button>
            </div>
            <div class="ai-input-content">
              <div class="ai-kind-choice" role="group" aria-label="物品情况">
                <button :class="{ active: aiKind === 'LOST' }" :aria-pressed="aiKind === 'LOST'" @click="aiKind = 'LOST'">我丢了物品</button>
                <button :class="{ active: aiKind === 'FOUND' }" :aria-pressed="aiKind === 'FOUND'" @click="aiKind = 'FOUND'">我捡到物品</button>
              </div>
              <label v-if="aiMode === 'text'" class="ai-description">
                <span class="visually-hidden">描述物品特征</span>
                <textarea v-model="aiDescription" maxlength="1200" placeholder="例如：我在图书馆自习区丢了一副黑色的蓝牙耳机，充电盒是圆角方形的，大概是今天下午 3 点之后不见的。"></textarea>
                <small>{{ aiDescription.length }} / 1200</small>
              </label>
              <div v-else class="ai-upload-zone">
                <label class="upload-drop" for="home-ai-image">
                  <img v-if="aiImagePreview" :src="aiImagePreview" alt="已选择的物品照片预览" />
                  <span v-else class="upload-plus">＋</span>
                  <strong>{{ aiImage ? aiImage.name : '点击选择物品照片' }}</strong>
                  <small>支持 JPG、PNG、WebP，单张不超过 8MB</small>
                </label>
                <input id="home-ai-image" type="file" accept="image/jpeg,image/png,image/webp" @change="onAiImageChange" />
              </div>
              <p v-if="aiError" class="ai-error" role="alert">{{ aiError }}</p>
              <button class="ai-submit" type="button" @click="startAiSearch"><AppIcon name="spark" />AI 智能匹配线索</button>
              <p class="ai-footnote">AI 提取的信息会先交由你人工核对，不会自动发布或认领。</p>
            </div>
          </section>

          <section class="ai-preview-card" aria-label="公开线索预览">
            <div class="ai-preview-heading">
              <h3><AppIcon name="search" />AI 匹配结果</h3>
              <span>确认物品信息后开始匹配</span>
            </div>
            <p class="ai-preview-intro">系统将综合物品特征、地点和时间，从当前校区的公开记录中寻找可能相关的线索。</p>
            <div v-if="previewItems.length" class="match-preview-list">
              <RouterLink v-for="item in previewItems" :key="item.id" :to="`/items/${item.id}`" class="match-preview-item">
                <ItemVisual :is-demo="item.is_demo" :image-note="item.image_note" :title="item.title" :category="item.category_name" :color="item.color" :image-url="item.image_url" />
                <div>
                  <span class="match-preview-tag">公开线索预览</span>
                  <strong>{{ item.title }}</strong>
                  <small><AppIcon name="map" />{{ item.location_name || '地点待核实' }} <span>·</span> {{ relativeTime(item.occurred_at) }}</small>
                </div>
                <AppIcon name="arrow" />
              </RouterLink>
            </div>
            <div v-else class="match-empty"><AppIcon name="spark" /><strong>等待你的第一条描述</strong><span>开始 AI 寻物后，匹配到的真实公开线索会显示在这里。</span></div>
            <p class="ai-preview-note">以上为当前校区公开线索预览，并非本次 AI 匹配结果。</p>
          </section>
        </div>
      </section>
    </section>
  </div>
</template>

<style scoped>
.home-page{width:100%;padding-bottom:28px;background:#f7f9fc;color:#17243b}
.home-hero{position:relative;isolation:isolate;overflow:hidden;min-height:328px;background:#dcecff url('/local-assets/campus-hero-generated.webp') center 53%/cover no-repeat}
.home-hero::before{position:absolute;z-index:-1;inset:0;content:"";background:linear-gradient(90deg,rgba(239,247,255,.96) 0%,rgba(239,247,255,.9) 32%,rgba(239,247,255,.4) 58%,rgba(239,247,255,.1) 100%),linear-gradient(0deg,rgba(239,247,255,.35),transparent 45%)}
.hero-inner{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(390px,.88fr);gap:42px;align-items:center;width:min(1360px,calc(100% - 80px));min-height:328px;margin:0 auto;padding:22px 0}
.hero-copy{min-width:0;padding:8px 0}
.home-label{margin:0 0 13px;color:#315f9f;font-size:14px;font-weight:700;letter-spacing:.02em}
.hero-copy h1{margin:0;color:#14243c;font-size:clamp(34px,3.25vw,47px);font-weight:850;line-height:1.25;letter-spacing:-.045em}
.hero-copy h1 span{position:relative;color:#1767dc;white-space:nowrap}
.hero-copy h1 span::after{position:absolute;right:0;bottom:-5px;left:0;height:5px;border-radius:100%;background:#20c4a5;content:"";transform:rotate(-2deg)}
.hero-verse{margin:17px 0 19px;color:#3e5875;font-size:16px;letter-spacing:.02em}
.hero-search{display:flex;align-items:center;gap:12px;width:min(100%,660px);height:48px;padding:4px 5px 4px 17px;border:1px solid rgba(63,125,205,.65);border-radius:28px;background:rgba(255,255,255,.94);box-shadow:0 7px 20px rgba(32,89,157,.09)}
.hero-search>svg{flex:0 0 auto;color:#6a7d98;font-size:19px}
.hero-search input{width:0;min-width:0;flex:1;border:0;outline:0;background:transparent;color:#263b57;font-size:13px}
.hero-search input::placeholder{color:#8492a7}
.hero-search button{align-self:stretch;min-width:84px;padding:0 19px;border:0;border-radius:24px;background:#2468e9;color:white;font-weight:700;cursor:pointer;box-shadow:0 3px 9px rgba(36,104,233,.18)}
.hero-actions{display:flex;flex-wrap:wrap;gap:14px;margin-top:15px}
.hero-actions .button{min-width:190px;min-height:44px;justify-content:center;border-radius:25px;font-size:14px;font-weight:750}
.hero-actions .button-brand{background:linear-gradient(100deg,#2677f6,#155ce3);box-shadow:0 7px 16px rgba(31,102,229,.2)}
.hero-actions .button-publish{border:1px solid rgba(40,179,164,.22);background:rgba(200,246,239,.9);color:#087d72}
.hero-trust{display:flex;flex-wrap:wrap;gap:22px;margin-top:13px;color:#52677f;font-size:12px}
.hero-trust span{display:inline-flex;align-items:center;gap:6px}
.hero-trust i{display:grid;place-items:center;width:15px;height:15px;border:1.5px solid #19b89b;border-radius:50%;color:#10a98d;font-size:10px;font-style:normal;font-weight:800}
.hero-board{min-width:0;padding:15px 16px 14px;border:1px solid rgba(255,255,255,.78);border-radius:22px;background:rgba(255,255,255,.82);box-shadow:0 14px 38px rgba(33,81,132,.1);backdrop-filter:blur(10px)}
.board-heading{display:flex;align-items:center;gap:9px;margin:0 2px 12px}
.board-icon{display:grid;place-items:center;width:26px;height:26px;border-radius:8px;background:#e7f1ff;color:#1767dc}
.board-heading h2{flex:1;margin:0;color:#182941;font-size:17px;font-weight:800}
.board-heading>a{display:flex;align-items:center;gap:3px;color:#58718f;font-size:12px;white-space:nowrap}
.hero-previews{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.preview-card{display:grid;grid-template-columns:76px minmax(0,1fr);gap:9px;align-items:center;min-width:0;min-height:83px;padding:8px;border:1px solid #edf2f8;border-radius:15px;background:rgba(255,255,255,.94);transition:transform .18s,border-color .18s,box-shadow .18s}
.preview-card:hover{transform:translateY(-2px);border-color:#cbdcf8;box-shadow:0 7px 18px rgba(38,88,150,.09)}
.preview-card :deep(.item-photo--thumbnail){width:76px;height:72px;border-radius:10px}
.preview-info{min-width:0}
.preview-info h3{overflow:hidden;margin:0 0 6px;color:#1e2d43;font-size:13px;font-weight:750;text-overflow:ellipsis;white-space:nowrap}
.preview-info p,.preview-info time{display:flex;align-items:center;gap:4px;margin:0;color:#728198;font-size:10px;line-height:1.5}
.preview-info p svg{flex:0 0 auto;font-size:11px}
.preview-info time{display:block;margin-top:2px}
.kind-pill{display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;width:max-content;padding:3px 8px;border-radius:999px;font-size:10px;font-weight:750;white-space:nowrap}
.preview-card .kind-pill{grid-column:2;justify-self:start;margin-top:-5px}
.kind-pill.is-found{background:#e1f8ee;color:#0b9a67}
.kind-pill.is-lost{background:#e5efff;color:#2769d7}
.board-state{display:grid;place-items:center;min-height:160px;margin:0;color:#6c7d93;font-size:13px}
.home-content{width:min(1360px,calc(100% - 80px));margin:0 auto}
.category-section{padding:13px 0 4px}
.section-heading{display:flex;align-items:center;justify-content:space-between;gap:18px;margin:0 0 12px}
.section-heading h2{display:flex;align-items:center;gap:10px;margin:0;color:#17263d;font-size:20px;font-weight:820;letter-spacing:-.02em}
.section-heading>a{display:inline-flex;align-items:center;gap:5px;color:#64758b;font-size:12px;white-space:nowrap}
.category-row{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:14px}
.category-row button{display:flex;align-items:center;gap:12px;min-width:0;min-height:70px;padding:10px 13px;border:1px solid #edf1f7;border-radius:16px;background:#fff;color:#17263d;text-align:left;cursor:pointer;box-shadow:0 4px 14px rgba(28,56,94,.035);transition:transform .16s,border-color .16s,box-shadow .16s}
.category-row button:hover,.category-row button.active{transform:translateY(-2px);border-color:#bfd5fb;box-shadow:0 8px 18px rgba(42,105,190,.09)}
.category-icon{display:grid;place-items:center;flex:0 0 auto;width:48px;height:48px;border-radius:50%;background:#e8f2ff;color:#2474e8;font-size:24px}
.category-row button:nth-child(2) .category-icon{background:#e2faf3;color:#0aaa7d}
.category-row button:nth-child(3) .category-icon{background:#fff1df;color:#f19b25}
.category-row button:nth-child(4) .category-icon{background:#f0eaff;color:#8b5be8}
.category-row button:nth-child(5) .category-icon{background:#e8f2ff;color:#2474e8}
.category-row button:nth-child(6) .category-icon{background:#e3f8ef;color:#10a778}
.category-copy{display:grid;gap:4px;min-width:0}
.category-copy strong{overflow:hidden;font-size:14px;font-weight:800;text-overflow:ellipsis;white-space:nowrap}
.category-copy small{overflow:hidden;color:#8290a4;font-size:10px;text-overflow:ellipsis;white-space:nowrap}
.latest-section{padding:15px 0 17px}
.latest-heading{margin-bottom:12px}
.latest-heading h2{gap:9px}
.heading-icon{display:grid;place-items:center;width:25px;height:25px;border-radius:50%;background:#2875ef;color:white;font-size:14px}
.latest-actions{display:flex;align-items:center;gap:18px}
.latest-tabs{display:flex;gap:3px;padding:3px;border:1px solid #e8edf5;border-radius:22px;background:#fff}
.latest-tabs button{padding:6px 14px;border:0;border-radius:18px;background:transparent;color:#6e7d91;font-size:12px;cursor:pointer}
.latest-tabs button.active{background:#286ff0;color:white;box-shadow:0 3px 8px rgba(40,111,240,.2)}
.latest-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
.latest-card{display:grid;grid-template-columns:122px minmax(0,1fr);gap:13px;align-items:center;min-width:0;min-height:145px;padding:11px;border:1px solid #e9eef6;border-radius:15px;background:#fff;box-shadow:0 5px 18px rgba(29,60,102,.045);transition:transform .16s,border-color .16s,box-shadow .16s}
.latest-card:hover{transform:translateY(-2px);border-color:#c8d9f4;box-shadow:0 10px 22px rgba(29,60,102,.08)}
.latest-card :deep(.item-photo--thumbnail){width:122px;height:122px;border-radius:11px}
.latest-body{display:flex;flex-direction:column;align-self:stretch;min-width:0;padding:2px 1px}
.latest-title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:6px}
.latest-title-row h3{overflow:hidden;margin:0;color:#182940;font-size:14px;font-weight:800;line-height:1.5;text-overflow:ellipsis;white-space:nowrap}
.latest-title-row .kind-pill{font-size:10px}
.latest-body>p{display:-webkit-box;overflow:hidden;margin:7px 0 8px;color:#63738a;font-size:11px;line-height:1.65;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.latest-meta{display:flex;flex-wrap:wrap;gap:5px 12px;margin-top:auto;color:#78869a;font-size:10px}
.latest-meta span,.latest-meta time{display:inline-flex;align-items:center;gap:4px;min-width:0}
.latest-meta svg{color:#70839c;font-size:12px}
.home-state{display:grid;place-items:center;align-content:center;min-height:140px;padding:24px;border:1px dashed #d9e3f0;border-radius:16px;background:#fff;color:#708096;text-align:center}
.home-state>svg{font-size:30px;color:#477fce}
.home-state p{line-height:1.7}
.partial-error{margin:9px 0 0;color:#9a6a20;font-size:12px}
.ai-workspace{margin:0 0 4px;padding:20px 22px 18px;border:1px solid #e0ebfb;border-radius:23px;background:linear-gradient(115deg,#edf4ff 0%,#e8f1ff 52%,#e4efff 100%);box-shadow:0 9px 26px rgba(44,103,179,.07)}
.ai-heading{display:flex;align-items:center;gap:12px;margin:0 0 15px}
.ai-robot{display:grid;place-items:center;flex:0 0 auto;width:48px;height:48px;border-radius:16px;background:linear-gradient(145deg,#fff,#dceaff);color:#2874ed;font-size:30px;box-shadow:0 6px 15px rgba(44,103,179,.13)}
.ai-heading h2{margin:0;color:#152c51;font-size:22px;font-weight:850;letter-spacing:-.025em}
.ai-heading p{margin:4px 0 0;color:#5f7390;font-size:12px}
.ai-heading-note{display:inline-flex;align-items:center;gap:6px;margin-left:auto;color:#6d809b;font-size:11px;white-space:nowrap}
.ai-heading-note svg{color:#2874ed}
.ai-workspace-grid{display:grid;grid-template-columns:minmax(0,.92fr) minmax(0,1.08fr);gap:22px;align-items:stretch}
.ai-input-card,.ai-preview-card{min-width:0;overflow:hidden;border:1px solid #dce7f7;border-radius:17px;background:rgba(255,255,255,.9);box-shadow:0 5px 16px rgba(45,87,142,.045)}
.ai-tabs{display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid #e5ebf5;background:#f9fbff}
.ai-tabs button{display:flex;align-items:center;justify-content:center;gap:7px;min-height:42px;border:0;border-bottom:3px solid transparent;background:transparent;color:#64758d;font-size:13px;font-weight:700;cursor:pointer}
.ai-tabs button.active{border-bottom-color:#2474ed;background:#fff;color:#1767dc}
.ai-input-content{padding:12px 14px 11px}
.ai-kind-choice{display:flex;gap:7px;margin-bottom:9px}
.ai-kind-choice button{padding:5px 11px;border:1px solid #e1e8f3;border-radius:16px;background:#fff;color:#687991;font-size:11px;cursor:pointer}
.ai-kind-choice button.active{border-color:#b8d2fa;background:#edf5ff;color:#246cdb;font-weight:750}
.ai-description{position:relative;display:block}
.ai-description textarea{display:block;width:100%;min-height:86px;resize:vertical;padding:11px 12px 24px;border:1px solid #dbe4f1;border-radius:11px;outline:0;background:#fff;color:#293c56;font-size:12px;line-height:1.7}
.ai-description textarea:focus{border-color:#75a8f5;box-shadow:0 0 0 3px rgba(45,118,232,.1)}
.ai-description textarea::placeholder{color:#8b99ac}
.ai-description small{position:absolute;right:10px;bottom:8px;color:#93a0b2;font-size:10px}
.ai-upload-zone{display:grid;min-height:86px}
.ai-upload-zone input{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;clip-path:inset(50%)}
.upload-drop{display:flex;align-items:center;justify-content:center;gap:8px;min-height:86px;padding:10px;border:1px dashed #a9c4ed;border-radius:11px;background:#f8fbff;color:#536b89;cursor:pointer}
.upload-drop img{width:62px;height:62px;object-fit:cover;border-radius:9px}
.upload-plus{display:grid;place-items:center;width:34px;height:34px;border-radius:10px;background:#e6f0ff;color:#286fe6;font-size:25px}
.upload-drop strong{max-width:240px;overflow:hidden;font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.upload-drop small{color:#8b99ac;font-size:10px}
.ai-submit{display:flex;align-items:center;justify-content:center;gap:8px;width:min(100%,370px);min-height:38px;margin:10px auto 0;border:0;border-radius:9px;background:linear-gradient(100deg,#2877f6,#155ee5);color:white;font-size:13px;font-weight:800;cursor:pointer;box-shadow:0 5px 13px rgba(33,104,224,.2)}
.ai-submit:hover{filter:brightness(1.04);transform:translateY(-1px)}
.ai-footnote{margin:7px 0 0;color:#8392a7;font-size:10px;text-align:center}
.ai-error{margin:6px 0 0;color:#bd3c3c;font-size:11px}
.ai-preview-card{padding:13px 14px 10px}
.ai-preview-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;padding-bottom:9px;border-bottom:1px solid #e8eef7}
.ai-preview-heading h3{display:flex;align-items:center;gap:8px;margin:0;color:#1b2e4b;font-size:16px;font-weight:820}
.ai-preview-heading h3 svg{color:#246fe7;font-size:21px}
.ai-preview-heading>span{padding:4px 8px;border-radius:14px;background:#edf4ff;color:#3474d0;font-size:10px;white-space:nowrap}
.ai-preview-intro{margin:9px 0 10px;color:#75849a;font-size:11px;line-height:1.55}
.match-preview-list{display:grid;gap:8px}
.match-preview-item{display:grid;grid-template-columns:76px minmax(0,1fr) 16px;gap:10px;align-items:center;min-width:0;padding:8px;border:1px solid #e8eef7;border-radius:12px;background:#fff;transition:border-color .16s,background .16s}
.match-preview-item:hover{border-color:#bfd4f5;background:#fbfdff}
.match-preview-item :deep(.item-photo--thumbnail){width:76px;height:66px;border-radius:8px}
.match-preview-item>div{display:grid;gap:4px;min-width:0}
.match-preview-item strong{overflow:hidden;color:#263a55;font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.match-preview-item small{display:flex;align-items:center;gap:4px;overflow:hidden;color:#78879c;font-size:10px;white-space:nowrap}
.match-preview-item small svg{flex:0 0 auto}
.match-preview-tag{width:max-content;padding:2px 7px;border-radius:9px;background:#e6f7ef;color:#1c9a70;font-size:9px;font-weight:750}
.match-preview-item>svg{color:#5b7eaf}
.ai-preview-note{margin:8px 0 0;color:#9aa6b6;font-size:9px}
.match-empty{display:grid;place-items:center;gap:6px;min-height:125px;color:#8292a8;text-align:center}
.match-empty svg{color:#4b82d5;font-size:25px}
.match-empty strong{color:#405775;font-size:13px}
.match-empty span{max-width:300px;font-size:10px;line-height:1.6}
.visually-hidden{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:1120px){.hero-inner,.home-content{width:calc(100% - 48px)}.hero-inner{grid-template-columns:minmax(0,1fr) minmax(340px,.88fr);gap:24px}.hero-copy h1{font-size:clamp(32px,4vw,43px)}.category-row{gap:9px}.category-row button{padding:9px}.category-icon{width:42px;height:42px}.latest-card{grid-template-columns:100px minmax(0,1fr)}.latest-card :deep(.item-photo--thumbnail){width:100px;height:112px}.ai-workspace-grid{gap:14px}}
@media(max-width:860px){.home-hero{min-height:auto}.hero-inner{grid-template-columns:1fr;gap:16px;padding:32px 0 24px}.hero-copy{max-width:720px}.hero-board{max-width:720px}.hero-previews{grid-template-columns:repeat(2,minmax(0,1fr))}.category-row{grid-template-columns:repeat(3,minmax(0,1fr))}.latest-grid{grid-template-columns:1fr}.latest-card{grid-template-columns:118px minmax(0,1fr)}.latest-card :deep(.item-photo--thumbnail){width:118px;height:118px}.ai-workspace-grid{grid-template-columns:1fr}.ai-heading-note{display:none}}
@media(max-width:560px){.hero-inner,.home-content{width:calc(100% - 28px)}.home-hero{background-position:60% center}.home-hero::before{background:linear-gradient(90deg,rgba(239,247,255,.95),rgba(239,247,255,.72)),linear-gradient(0deg,rgba(239,247,255,.4),transparent)}.hero-inner{padding:25px 0 19px}.home-label{font-size:12px}.hero-copy h1{font-size:34px}.hero-verse{margin:12px 0 15px;font-size:13px}.hero-search{height:44px;padding-left:12px;gap:8px}.hero-search input{font-size:11px}.hero-search button{min-width:60px;padding:0 12px;font-size:12px}.hero-actions{gap:9px}.hero-actions .button{min-width:0;flex:1;min-height:42px;font-size:12px}.hero-trust{gap:9px 14px;font-size:10px}.hero-board{padding:12px;border-radius:16px}.board-heading h2{font-size:15px}.hero-previews{gap:7px}.preview-card{grid-template-columns:58px minmax(0,1fr);gap:7px;min-height:72px;padding:6px;border-radius:11px}.preview-card :deep(.item-photo--thumbnail){width:58px;height:58px}.preview-info h3{font-size:11px}.preview-info p,.preview-info time{font-size:9px}.preview-card .kind-pill{font-size:8px;padding:2px 6px}.category-section{padding-top:13px}.section-heading h2{font-size:17px}.category-row{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.category-row button{min-height:62px;padding:8px;border-radius:12px}.category-icon{width:39px;height:39px;font-size:20px}.category-copy strong{font-size:12px}.category-copy small{font-size:9px}.latest-section{padding-top:12px}.latest-heading{align-items:flex-start;flex-direction:column}.latest-actions{width:100%;justify-content:space-between;gap:8px}.latest-tabs button{padding:6px 9px;font-size:10px}.latest-actions>a{font-size:10px}.latest-card{grid-template-columns:94px minmax(0,1fr);gap:9px;min-height:112px;padding:8px}.latest-card :deep(.item-photo--thumbnail){width:94px;height:94px}.latest-title-row h3{font-size:12px}.latest-title-row .kind-pill{font-size:8px;padding:2px 6px}.latest-body>p{margin:4px 0;font-size:10px}.latest-meta{font-size:9px}.ai-workspace{padding:14px 10px;border-radius:17px}.ai-heading{gap:9px;margin-bottom:11px}.ai-robot{width:38px;height:38px;border-radius:12px;font-size:24px}.ai-heading h2{font-size:18px}.ai-heading p{font-size:10px;line-height:1.5}.ai-input-content{padding:10px}.ai-preview-card{padding:11px}.ai-preview-heading h3{font-size:14px}.ai-preview-heading>span{font-size:9px}.match-preview-item{grid-template-columns:64px minmax(0,1fr) 12px;padding:6px;gap:8px}.match-preview-item :deep(.item-photo--thumbnail){width:64px;height:58px}.match-preview-item strong{font-size:11px}}
@media(prefers-reduced-motion:reduce){.preview-card:hover,.category-row button:hover,.latest-card:hover,.ai-submit:hover{transform:none}}
</style>
