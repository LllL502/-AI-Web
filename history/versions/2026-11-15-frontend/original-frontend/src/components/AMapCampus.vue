<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { api } from '../api/client'
import { loadAMap } from '../api/amap'
import DemoCampusMap, { type DemoMapLocation } from './DemoCampusMap.vue'
type CoordinatePoint={latitude:number;longitude:number;label?:string;coordinate_system?:'GCJ02'}
type MapPlace={name:string;address:string;latitude:number;longitude:number}
const props=withDefaults(defineProps<{pickable?:boolean;compact?:boolean;selectedPreciseLocation?:string;selectedProtectedLocationIds?:number[];selectedCoordinatePoints?:CoordinatePoint[]}>(),{pickable:false,compact:false,selectedPreciseLocation:'',selectedProtectedLocationIds:()=>[],selectedCoordinatePoints:()=>[]})
const emit=defineEmits<{pick:[point:CoordinatePoint];'select-protected-location':[location:DemoMapLocation];'select-map-place':[place:MapPlace]}>()
const container=ref<HTMLElement|null>(null), loading=ref(true), message=ref(''), term=ref(''), searchBusy=ref(false)
const candidates=ref<{id:string;name:string;address:string;location:any}[]>([])
const campusPending=ref(false)
const isDemo=ref(false)
const demoLocations=ref<DemoMapLocation[]>([])
const selectedDemoIds=computed(()=>{
  const selected=new Set(props.selectedProtectedLocationIds)
  const legacy=demoLocations.value.find((entry)=>entry.name===props.selectedPreciseLocation)?.id
  if(legacy)selected.add(legacy)
  return [...selected]
})
let map:any=null, provider:any=null, searcher:any=null, markers:any[]=[], disposed=false
let generation=0
let searchTimer:ReturnType<typeof setTimeout>|undefined
let campusLabel=''
async function search(keyword=term.value){
  if(!searcher||!keyword.trim())return
  const revision=++generation
  clearTimeout(searchTimer)
  searchBusy.value=true;message.value=''
  searchTimer=setTimeout(()=>{if(!disposed&&revision===generation){searchBusy.value=false;message.value='地点搜索超时，请检查地图授权或网络后重试。';generation++}},10000)
  searcher.search(keyword,(status:string,result:any)=>{
    if(disposed||revision!==generation)return
    clearTimeout(searchTimer)
    searchBusy.value=false
    candidates.value=status==='complete'?(result.poiList?.pois??[]).filter((p:any)=>p.location):[]
    if(!candidates.value.length)message.value='没有找到地点，请尝试更完整的校区或楼宇名称。'
    // 搜索结果是地图候选，需用户核对，不把首条结果自动认定为校区。
    if(candidates.value[0])map.setZoomAndCenter(15,candidates.value[0].location)
  })
}
function renderMarkers(points:CoordinatePoint[]){
  if(!map||!provider)return
  if(markers.length)map.remove(markers)
  markers=points.map((point,index)=>new provider.Marker({
    position:[point.longitude,point.latitude],
    title:point.label||`候选地点 ${index+1}`,
    label:{direction:'top',content:`<span class="ct-map-rank">${index+1}</span>`},
  }))
  if(markers.length)map.add(markers)
}
function pick(latitude:number,longitude:number,label='地图选点'){
  if(props.pickable)emit('pick',{latitude,longitude,label,coordinate_system:'GCJ02'})
}
function selectPOI(poi:any){
  map.setZoomAndCenter(17,poi.location)
  emit('select-map-place',{
    name:poi.name,
    address:poi.address||'',
    latitude:poi.location.getLat(),
    longitude:poi.location.getLng(),
  })
  pick(poi.location.getLat(),poi.location.getLng(),poi.name)
  message.value=props.pickable?`已加入候选：${poi.name}`:`正在查看：${poi.name}`
}
async function start(){
  loading.value=true;message.value=''
  try{
    const config=await api<{data:{enabled:boolean;web_key:string;service_host:string;notice:string;campus:{name:string;school:string;city:string;verified:boolean;is_demo:boolean}}}>('/maps/config/')
    if(disposed)return
    isDemo.value=Boolean(config.data.campus?.is_demo)
    if(isDemo.value){
      // 演示校区没有真实坐标，改用公开线索地点与服务站生成的虚拟布局。
      // 这样既不会把虚构坐标发送给高德，也能完整演示地点选择流程。
      const summary=await api<{data:{locations:DemoMapLocation[]}}>('/items/map-summary/')
      if(disposed)return
      demoLocations.value=summary.data.locations
      if(!demoLocations.value.length)message.value='演示校区暂时没有可展示的公开地点。'
      return
    }
    campusPending.value=!config.data.campus?.verified&&!config.data.campus?.is_demo
    if(!config.data.enabled){message.value=config.data.notice;return}
    provider=await loadAMap(config.data.web_key,config.data.service_host)
    if(disposed||!container.value)return
    map=new provider.Map(container.value,{zoom:4,viewMode:'2D',center:[105,35]})
    map.addControl(new provider.Scale());map.addControl(new provider.ToolBar())
    renderMarkers(props.selectedCoordinatePoints)
    searcher=new provider.PlaceSearch({pageSize:5,city:config.data.campus.city||'全国',citylimit:!!config.data.campus.city})
    // 未核实的“主校区”是占位名称，不能用作真实校区的搜索限定。
    campusLabel=campusPending.value&&config.data.campus.name==='主校区'?config.data.campus.school:`${config.data.campus.school} ${config.data.campus.name==='校本部'?'':config.data.campus.name}`.trim()
    term.value=campusLabel
    if(props.pickable)map.on('click',(event:any)=>pick(event.lnglat.getLat(),event.lnglat.getLng(),`地图选点 ${props.selectedCoordinatePoints.length+1}`))
    search(campusLabel)
  }catch{message.value='地图加载失败，仍可使用文字地点。请检查网络后重试。'}finally{loading.value=false}
}
function retry(){if(map){map.destroy();map=null};start()}
function selectDemoLocation(location:DemoMapLocation){emit('select-protected-location',location)}
watch(()=>props.selectedCoordinatePoints,(points)=>renderMarkers(points),{deep:true})
onMounted(start)
onBeforeUnmount(()=>{disposed=true;generation++;clearTimeout(searchTimer);markers=[];map?.destroy();map=null})
</script>
<template>
<DemoCampusMap v-if="isDemo&&!loading&&demoLocations.length" :locations="demoLocations" :selected-ids="selectedDemoIds" @select="selectDemoLocation" />
<section v-else class="amap-shell" :class="{compact}" :aria-label="isDemo?'演示校区虚拟地图':'真实校园地图'">
  <!-- 地图可能嵌套在发布表单中，因此这里不能再使用 form，也不能让按钮采用默认 submit 类型。 -->
  <div v-if="map&&!compact" class="map-search"><input v-model="term" aria-label="搜索校园地点" placeholder="输入完整学校、校区或楼宇名称" @keydown.enter.prevent="search()"/><button class="button button-ghost" type="button" :disabled="searchBusy" @click="search()">{{searchBusy?'搜索中…':'搜索地点'}}</button></div>
  <div ref="container" class="map-canvas" aria-label="高德地图画布"></div>
  <div v-if="loading" class="map-state" role="status">正在加载校园地图…</div>
  <div v-if="!loading&&!map" class="map-state"><strong>{{isDemo?'演示校区虚拟地图':'真实校园地图'}}</strong><p>{{message}}</p><button v-if="!isDemo" class="button button-ghost" type="button" @click="retry">重试加载</button></div>
  <div v-if="map" class="map-info"><small>{{pickable?'点击地图或下方地点可加入候选位置':'搜索校园地点'}}</small><p v-if="message" role="status">{{message}}</p><div class="poi-results"><button v-for="poi in candidates" :key="poi.id" type="button" @click="selectPOI(poi)">{{poi.name}} <small>{{poi.address}}</small></button></div></div>
</section>
</template>
<style scoped>
.campus-notice{position:relative;z-index:2;margin:0;padding:12px 16px;background:var(--ct-surface);color:var(--ct-accent,#f5bd41);font-size:13px;line-height:1.6}
.amap-shell{position:relative;border:1px solid var(--ct-border);border-radius:18px;overflow:hidden;background:var(--ct-surface);min-height:440px}.map-canvas{width:100%;height:440px}.compact .map-canvas{height:440px}.map-state{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:12px;padding:28px;color:var(--ct-text-muted);text-align:center;background:var(--ct-bg-soft)}.map-state strong{font-size:23px;color:var(--ct-text)}.map-search{display:flex;gap:8px;padding:12px}.map-search input{min-width:0;flex:1;padding:10px;border:1px solid var(--ct-border);border-radius:8px;background:var(--ct-bg);color:var(--ct-text)}.map-info{padding:14px;line-height:1.6;color:var(--ct-text-muted)}.poi-results{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}.poi-results button{padding:8px;border:1px solid var(--ct-border);border-radius:8px;background:var(--ct-bg);color:var(--ct-text);text-align:left;cursor:pointer}.poi-results small{display:block}.compact .poi-results{max-height:100px;overflow:auto}@media(max-width:620px){.map-canvas,.compact .map-canvas{height:340px}.amap-shell{min-height:340px}}
:deep(.ct-map-rank){display:grid;place-items:center;width:22px;height:22px;border:2px solid #fff;border-radius:50%;background:var(--ct-brand,#9d302d);color:#fff;font:700 12px/1 sans-serif;box-shadow:0 2px 7px rgba(0,0,0,.3)}
</style>
