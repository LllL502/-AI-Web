<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { apiCached, ApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'
import AMapCampus from '../../components/AMapCampus.vue'
import DemoCampusMap, { type DemoMapLocation } from '../../components/DemoCampusMap.vue'

type Campus = { id: number; name: string; school: string; is_demo: boolean }
type PublicStation = { id: number; name: string; status: string; address: string }
type MapPlace = { name: string; address: string; latitude: number; longitude: number }
type MapResponse = { data: { campus: Campus; total: number; kind_totals: { LOST: number; FOUND: number }; stations: PublicStation[]; locations: DemoMapLocation[] } }

const locations = ref<DemoMapLocation[]>([])
const campus = ref<Campus | null>(null)
const total = ref(0)
const kindTotals = ref({ LOST: 0, FOUND: 0 })
const campusStations = ref<PublicStation[]>([])
const selectedMapPlace = ref<MapPlace | null>(null)
const selectedId = ref<number | null>(null)
const loading = ref(true)
const error = ref('')

const selectedLocation = computed(() => locations.value.find((entry) => entry.id === selectedId.value) ?? locations.value[0] ?? null)
const hotspots = computed(() => [...locations.value].filter((entry) => entry.count > 0).sort((left, right) => right.count - left.count).slice(0, 7))
const mapLead = computed(() => campus.value === null
  ? '正在加载校园地图。'
  : campus.value.is_demo
    ? '查看演示校区的公开线索与服务站。'
    : '搜索校园地点，查看当前校区的公开线索与服务站。')
const stationStatus = (status: string) => ({ OPEN: '开放', BUSY: '繁忙', CLOSED: '暂停服务' }[status] ?? status)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await apiCached<MapResponse>('/items/map-summary/')
    campus.value = response.data.campus
    locations.value = response.data.locations
    total.value = response.data.total
    kindTotals.value = response.data.kind_totals ?? { LOST: 0, FOUND: 0 }
    campusStations.value = response.data.stations ?? []
    if (!locations.value.some((entry) => entry.id === selectedId.value)) selectedId.value = hotspots.value[0]?.id ?? locations.value[0]?.id ?? null
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '地图数据加载失败'
  } finally {
    loading.value = false
  }
}

function selectLocation(location: DemoMapLocation) { selectedId.value = location.id }
function selectMapPlace(place: MapPlace) { selectedMapPlace.value = place }

onMounted(load)
</script>

<template>
  <div class="page map-page">
    <header class="map-header">
      <div><h1 class="page-title">校园线索地图</h1><p class="page-lead">{{ mapLead }}</p></div>
    </header>
    <p v-if="loading" class="state" role="status">正在生成校园线索地图…</p>
    <p v-else-if="error" class="state error" role="alert">{{ error }}</p>
    <div v-else class="map-layout">
      <DemoCampusMap v-if="campus?.is_demo" :locations="locations" :selected-id="selectedLocation?.id" @select="selectLocation" />
      <AMapCampus v-else @select-map-place="selectMapPlace" />
      <aside class="panel area-panel" :class="{ 'real-panel': campus && !campus.is_demo }">
        <span class="status-tag">公开线索 · {{ total }} 条</span>
        <template v-if="campus && !campus.is_demo">
          <p class="selection-kicker">当前校区</p>
          <h2>{{ campus.school }} · {{ campus.name }}</h2>
          <div class="campus-stats" aria-label="当前校区公开线索统计">
            <div><strong>{{ kindTotals.LOST }}</strong><span>遗失</span></div>
            <div><strong>{{ kindTotals.FOUND }}</strong><span>招领</span></div>
          </div>
          <section v-if="selectedMapPlace" class="viewed-place">
            <p class="selection-kicker">当前查看地点</p>
            <strong>{{ selectedMapPlace.name }}</strong>
            <small>{{ selectedMapPlace.address || '校内地点' }}</small>
          </section>
          <p v-else class="map-hint">点击地图下方的搜索结果，这里会同步显示地点信息。</p>
          <section v-if="campusStations.length" class="station-list" aria-label="校园服务站">
            <p class="selection-kicker">校园服务站</p>
            <RouterLink v-for="station in campusStations" :key="station.id" :to="`/stations/${station.id}`" class="station-card">
              <span class="station-mark">站</span><span><strong>{{ station.name }}</strong><small>{{ station.address }} · {{ stationStatus(station.status) }}</small></span><AppIcon name="arrow" />
            </RouterLink>
          </section>
          <section v-if="total === 0" class="real-empty">
            <AppIcon name="map" />
            <h3>当前校区暂无公开线索</h3>
            <p>你可以发布第一条信息，地图会在审核通过后更新统计。</p>
            <div><RouterLink to="/publish/lost">发布遗失</RouterLink><RouterLink to="/publish/found">登记招领</RouterLink></div>
          </section>
        </template>
        <template v-else-if="selectedLocation">
          <p class="selection-kicker">当前选中区域</p>
          <h2>{{ selectedLocation.name }}</h2>
          <p>该区域共有 <strong>{{ selectedLocation.count }}</strong> 条公开线索。为保护隐私，地图不显示物品精确标点。</p>
          <section v-if="selectedLocation.stations.length" class="station-list" aria-label="区域服务站">
            <p class="selection-kicker">校园服务站</p>
            <RouterLink v-for="station in selectedLocation.stations" :key="station.id" :to="`/stations/${station.id}`" class="station-card">
              <span class="station-mark">站</span><span><strong>{{ station.name }}</strong><small>{{ station.address }} · {{ stationStatus(station.status) }}</small></span><AppIcon name="arrow" />
            </RouterLink>
          </section>
        </template>
        <template v-if="campus?.is_demo">
          <div class="hotspot-head"><span>线索热点</span><small>点击定位</small></div>
          <ol><li v-for="(entry, index) in hotspots" :key="entry.id"><button type="button" :class="{ active: selectedLocation?.id === entry.id }" @click="selectLocation(entry)"><span>{{ String(index + 1).padStart(2, '0') }}</span><b>{{ entry.name }}</b><small>{{ entry.count }} 条</small></button></li></ol>
        </template>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.map-header{margin-bottom:32px}.map-layout{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:18px}.area-panel{padding:24px;box-shadow:none}.selection-kicker{margin:22px 0 5px!important;color:var(--ct-brand)!important;font-size:10px!important;font-weight:800;letter-spacing:.12em}.area-panel h2{margin:0 0 10px;font-size:23px}.area-panel>p{color:var(--ct-text-muted);line-height:1.7}.area-panel>p strong{color:var(--ct-brand);font-size:18px}.campus-stats{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:16px}.campus-stats div{padding:14px;border:1px solid var(--ct-border);border-radius:11px;background:var(--ct-bg-soft)}.campus-stats strong,.campus-stats span{display:block}.campus-stats strong{color:var(--ct-brand);font-size:24px}.campus-stats span{margin-top:3px;color:var(--ct-text-muted);font-size:11px}.viewed-place{margin-top:18px;padding:0 0 16px;border-bottom:1px solid var(--ct-border)}.viewed-place>.selection-kicker{margin-top:0!important}.viewed-place>strong,.viewed-place>small{display:block}.viewed-place>small{margin-top:5px;color:var(--ct-text-muted)}.map-hint{margin:18px 0 0;padding:14px;border:1px dashed var(--ct-border);border-radius:11px;color:var(--ct-text-muted);font-size:12px;line-height:1.65}.real-empty{display:grid;place-items:center;margin-top:18px;padding:22px 12px;border:1px dashed var(--ct-border);border-radius:13px;text-align:center}.real-empty>svg{color:var(--ct-brand);font-size:28px}.real-empty h3{margin:10px 0 3px}.real-empty p{margin:0;color:var(--ct-text-muted);font-size:12px;line-height:1.6}.real-empty>div{display:flex;gap:8px;margin-top:14px}.real-empty a{padding:8px 11px;border:1px solid var(--ct-border-strong);border-radius:8px;color:var(--ct-brand)}.station-list{margin-top:18px;padding-top:1px;border-top:1px solid var(--ct-border)}.station-card{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:10px;margin-top:9px;padding:11px;border:1px solid var(--ct-border);border-radius:10px;background:var(--ct-bg-soft);color:var(--ct-text)}.station-mark{display:grid;place-items:center;width:31px;height:31px;border-radius:50%;background:var(--ct-brand);color:#fff;font-weight:800}.station-card strong,.station-card small{display:block}.station-card small{margin-top:4px;color:var(--ct-text-muted);font-size:10px}.station-card>svg{color:var(--ct-brand)}.hotspot-head{display:flex;justify-content:space-between;margin-top:24px;padding-top:18px;border-top:1px solid var(--ct-border);font-size:12px;font-weight:800}.hotspot-head small{color:var(--ct-text-muted);font-weight:400}.area-panel ol{margin:8px 0 0;padding:0;list-style:none}.area-panel li+li{border-top:1px solid var(--ct-border)}.area-panel li button{display:grid;width:100%;grid-template-columns:28px 1fr auto;gap:8px;padding:11px 4px;color:var(--ct-text);border:0;background:transparent;text-align:left;cursor:pointer}.area-panel li button>span{color:var(--ct-brand)}.area-panel li button>b{font-size:12px}.area-panel li button>small{color:var(--ct-text-muted)}.area-panel li button.active b{color:var(--ct-brand)}.state{display:grid;place-items:center;min-height:430px;color:var(--ct-text-muted)}.error{color:var(--ct-danger)}
@media(max-width:1050px){.map-layout{grid-template-columns:1fr}.area-panel{display:grid;grid-template-columns:1fr 1fr;column-gap:24px}.area-panel.real-panel{display:block}.area-panel>.status-tag,.area-panel>.selection-kicker,.area-panel>h2,.area-panel>p{grid-column:1}.station-list{grid-column:1}.hotspot-head,.area-panel>ol{grid-column:2}.hotspot-head{grid-row:2;margin-top:22px}.area-panel>ol{grid-row:3/8}}
@media(max-width:700px){.map-header{align-items:start;flex-direction:column}.area-panel{display:block}}
</style>
