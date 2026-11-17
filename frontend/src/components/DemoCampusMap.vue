<script setup lang="ts">
import { computed } from 'vue'

export interface DemoStation {
  id: number
  name: string
  status: string
  address: string
}

export interface DemoMapLocation {
  id: number
  name: string
  code: string
  count: number
  stations: DemoStation[]
}

const props = withDefaults(defineProps<{ locations: DemoMapLocation[]; selectedId?: number | null; selectedIds?: number[] }>(), {
  selectedId: null,
  selectedIds: () => [],
})
const emit = defineEmits<{ select: [location: DemoMapLocation] }>()

type Zone = 'learning' | 'living' | 'sports' | 'service' | 'gate' | 'scenic'
type PositionedLocation = DemoMapLocation & { x: number; y: number; zone: Zone }

const slots: Record<Zone, Array<[number, number]>> = {
  learning: [[22, 23], [34, 20], [46, 25], [29, 35], [43, 38], [53, 31]],
  living: [[15, 53], [27, 55], [39, 54], [20, 68], [34, 70]],
  sports: [[59, 68], [73, 70], [86, 63], [72, 58]],
  service: [[62, 20], [75, 22], [87, 28], [65, 36], [80, 39], [55, 49], [89, 48]],
  gate: [[50, 7], [95, 47], [50, 91], [5, 47]],
  scenic: [[49, 56], [54, 61]],
}

function zoneFor(name: string): Zone {
  if (/门$/.test(name)) return 'gate'
  if (/宿舍|公寓/.test(name)) return 'living'
  if (/体育|田径|游泳/.test(name)) return 'sports'
  if (/教学|实验|图书馆/.test(name)) return 'learning'
  if (/湖|广场/.test(name)) return 'scenic'
  return 'service'
}

const gateCoordinates: Record<string, [number, number]> = {
  北门: [50, 7],
  东门: [95, 47],
  南门: [50, 91],
  西门: [5, 47],
}

const positioned = computed<PositionedLocation[]>(() => {
  const indexes: Record<Zone, number> = { learning: 0, living: 0, sports: 0, service: 0, gate: 0, scenic: 0 }
  return [...props.locations]
    .sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'))
    .map((location) => {
      const zone = zoneFor(location.name)
      const index = indexes[zone]++
      const options = slots[zone]
      const fallback: [number, number] = [12 + (index % 7) * 12, 15 + Math.floor(index / 7) * 12]
      const [x, y] = gateCoordinates[location.name] ?? options[index] ?? fallback
      return { ...location, x, y, zone }
    })
})

const activeIds = computed(() => new Set([
  ...(props.selectedIds ?? []),
  ...(props.selectedId == null ? [] : [props.selectedId]),
]))
</script>

<template>
  <section class="virtual-map" aria-label="演示校区虚拟地图">
    <div class="map-ribbon"><strong>演示校区 · 虚拟布局</strong><span>由公开线索地点与服务站数据自动生成</span></div>
    <div class="map-stage">
      <svg class="map-base" viewBox="0 0 1000 620" aria-hidden="true">
        <defs>
          <pattern id="demo-grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="currentColor" stroke-opacity=".055" /></pattern>
          <linearGradient id="demo-lake" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#bddbd6"/><stop offset="1" stop-color="#d8e8de"/></linearGradient>
        </defs>
        <rect width="1000" height="620" rx="24" fill="url(#demo-grid)" />
        <path class="road main-road" d="M45 292H955M505 42V578" />
        <path class="road minor-road" d="M95 440C265 405 372 425 505 475S760 520 920 465M110 125C275 170 380 135 505 110S750 90 900 155" />
        <path class="lake" d="M430 315c53-29 108-22 142 7 29 25 23 73-18 92-47 22-133 5-151-36-10-23 2-49 27-63Z" />
        <g class="buildings">
          <rect x="145" y="110" width="118" height="70" rx="9" />
          <rect x="300" y="94" width="118" height="86" rx="9" />
          <rect x="615" y="100" width="105" height="76" rx="9" />
          <rect x="748" y="120" width="105" height="66" rx="9" />
          <rect x="112" y="356" width="116" height="72" rx="9" />
          <rect x="256" y="365" width="120" height="76" rx="9" />
          <rect x="650" y="390" width="205" height="105" rx="36" />
        </g>
        <text x="204" y="150">教学区</text><text x="669" y="143">公共服务区</text><text x="180" y="398">生活区</text><text x="715" y="447">运动区</text>
      </svg>
      <button
        v-for="location in positioned"
        :key="location.id"
        type="button"
        class="map-node"
        :class="[{ active: activeIds.has(location.id), station: location.stations.length }, `zone-${location.zone}`]"
        :style="{ left: `${location.x}%`, top: `${location.y}%` }"
        :aria-label="`${location.name}，${location.count} 条公开线索${location.stations.length ? `，${location.stations.length} 个服务站` : ''}`"
        @click="emit('select', location)"
      >
        <span class="node-dot"><b v-if="location.stations.length">站</b><b v-else>{{ location.count }}</b></span>
        <span class="node-label">{{ location.name }}</span>
      </button>
      <div class="map-compass" aria-hidden="true"><span>北</span><i></i></div>
    </div>
    <footer class="map-legend"><span><i class="legend-dot clue"></i>数字为公开线索数</span><span><i class="legend-dot station"></i>“站”为校园服务站</span><span>虚拟布局不代表真实地理坐标</span></footer>
  </section>
</template>

<style scoped>
.virtual-map{overflow:hidden;border:1px solid var(--ct-border);border-radius:18px;background:var(--ct-surface);box-shadow:0 12px 30px rgba(70,48,28,.06)}
.map-ribbon{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:13px 18px;border-bottom:1px solid var(--ct-border);background:rgba(141,48,46,.055)}
.map-ribbon strong{color:var(--ct-brand);font:700 15px 'Songti SC','SimSun',serif}.map-ribbon span{color:var(--ct-text-muted);font-size:11px}
.map-stage{position:relative;min-height:520px;overflow:hidden;background:#f3efe6}
.map-base{position:absolute;inset:0;width:100%;height:100%;color:#675c4e}.road{fill:none;stroke:#fffdf8;stroke-linecap:round}.main-road{stroke-width:34}.minor-road{stroke-width:18}.lake{fill:url(#demo-lake);stroke:#94bbb4;stroke-width:2}.buildings rect{fill:#e2d7c5;stroke:#cdbda4;stroke-width:2}.map-base text{fill:#9b8e79;font:18px 'Songti SC','SimSun',serif;text-anchor:middle;letter-spacing:3px}
.map-node{position:absolute;z-index:2;display:flex;align-items:center;gap:7px;max-width:116px;padding:0;border:0;background:transparent;color:var(--ct-text);transform:translate(-50%,-50%);cursor:pointer;text-align:left}.node-dot{display:grid;flex:0 0 auto;place-items:center;width:31px;height:31px;border:3px solid #fffdf8;border-radius:50%;background:var(--ct-info);color:#fff;font:700 11px/1 Arial,sans-serif;box-shadow:0 3px 11px rgba(38,92,76,.28)}.node-label{padding:4px 6px;border:1px solid rgba(205,189,164,.9);border-radius:6px;background:rgba(255,253,248,.93);font:700 10px/1.25 'Songti SC','SimSun',serif;white-space:nowrap;box-shadow:0 2px 8px rgba(70,48,28,.08)}.map-node:hover,.map-node.active{z-index:5}.map-node:hover .node-dot,.map-node.active .node-dot{transform:scale(1.18);outline:3px solid rgba(141,48,46,.18)}.map-node.active .node-label{color:var(--ct-brand);border-color:var(--ct-brand)}.map-node.station .node-dot{width:36px;height:36px;background:var(--ct-brand);box-shadow:0 4px 13px rgba(141,48,46,.3)}
.map-compass{position:absolute;right:18px;top:18px;display:grid;place-items:center;width:42px;height:55px;color:var(--ct-brand);font:700 11px serif}.map-compass i{display:block;width:0;height:0;margin-top:4px;border-right:8px solid transparent;border-bottom:22px solid var(--ct-brand);border-left:8px solid transparent}
.map-legend{display:flex;flex-wrap:wrap;gap:12px 22px;padding:12px 18px;color:var(--ct-text-muted);font-size:10px;border-top:1px solid var(--ct-border)}.map-legend span{display:flex;align-items:center;gap:7px}.legend-dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--ct-info)}.legend-dot.station{background:var(--ct-brand)}
@media(max-width:760px){.map-ribbon{align-items:flex-start;flex-direction:column}.map-stage{min-height:470px}.node-label{display:none}.map-node.active .node-label,.map-node:hover .node-label{display:block}.map-legend{gap:9px}}
</style>
