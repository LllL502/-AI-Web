<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api/client'
import { loadAMap } from '../api/amap'
const props=withDefaults(defineProps<{pickable?:boolean;compact?:boolean}>(),{pickable:false,compact:false})
const emit=defineEmits<{pick:[point:{latitude:number;longitude:number}]}>()
const container=ref<HTMLElement|null>(null), loading=ref(true), message=ref(''), term=ref(''), searchBusy=ref(false)
const candidates=ref<{id:string;name:string;address:string;location:any}[]>([])
const campusPending=ref(false)
let map:any=null, provider:any=null, searcher:any=null, marker:any=null, disposed=false
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
function pick(latitude:number,longitude:number){
  if(marker)map.remove(marker)
  marker=new provider.Marker({position:[longitude,latitude]});map.add(marker)
  if(props.pickable)emit('pick',{latitude,longitude})
}
function selectPOI(poi:any){
  map.setZoomAndCenter(17,poi.location)
  pick(poi.location.getLat(),poi.location.getLng())
  message.value=`已查看：${poi.name}。请核对是否属于所选校区。`
}
async function start(){
  loading.value=true;message.value=''
  try{
    const config=await api<{data:{enabled:boolean;web_key:string;service_host:string;notice:string;campus:{name:string;school:string;city:string;verified:boolean;is_demo:boolean}}}>('/maps/config/')
    if(disposed)return
    campusPending.value=!config.data.campus?.verified&&!config.data.campus?.is_demo
    if(!config.data.enabled){message.value=config.data.notice;return}
    provider=await loadAMap(config.data.web_key,config.data.service_host)
    if(disposed||!container.value)return
    map=new provider.Map(container.value,{zoom:4,viewMode:'2D',center:[105,35]})
    map.addControl(new provider.Scale());map.addControl(new provider.ToolBar())
    searcher=new provider.PlaceSearch({pageSize:5,city:config.data.campus.city||'全国',citylimit:!!config.data.campus.city})
    // 未核实的“主校区”是占位名称，不能用作真实校区的搜索限定。
    campusLabel=campusPending.value?config.data.campus.school:`${config.data.campus.school} ${config.data.campus.name==='校本部'?'':config.data.campus.name}`.trim()
    term.value=campusLabel
    if(props.pickable)map.on('click',(event:any)=>pick(event.lnglat.getLat(),event.lnglat.getLng()))
    search(campusLabel)
  }catch{message.value='地图加载失败，仍可使用文字地点。请检查网络后重试。'}finally{loading.value=false}
}
function retry(){if(map){map.destroy();map=null};start()}
onMounted(start)
onBeforeUnmount(()=>{disposed=true;generation++;clearTimeout(searchTimer);map?.destroy();map=null})
</script>
<template><section class="amap-shell" :class="{compact}" aria-label="真实校园地图">
  <p v-if="campusPending" class="campus-notice" role="note">校区资料待核实：按学校名称搜索，请核对真实地点；搜索结果不会自动写入校区资料。</p>
  <form v-if="map&&!compact" class="map-search" @submit.prevent="search()"><input v-model="term" aria-label="搜索校园地点" placeholder="输入完整学校、校区或楼宇名称"/><button class="button button-ghost" :disabled="searchBusy">{{searchBusy?'搜索中…':'搜索地点'}}</button></form>
  <div ref="container" class="map-canvas" aria-label="高德地图画布"></div>
  <div v-if="loading" class="map-state" role="status">正在加载校园地图…</div>
  <div v-if="!loading&&!map" class="map-state"><strong>真实校园地图</strong><p>{{message}}</p><button class="button button-ghost" @click="retry">重试加载</button></div>
  <div v-if="map" class="map-info"><small>{{pickable?'点击地图选择精确位置；标点仅用于受保护的物品位置':'地图搜索结果供核对，未确认的地点不作为实际服务站'}}</small><p v-if="message" role="status">{{message}}</p><div class="poi-results"><button v-for="poi in candidates" :key="poi.id" @click="selectPOI(poi)">{{poi.name}} <small>{{poi.address}}</small></button></div></div>
</section></template>
<style scoped>
.campus-notice{position:relative;z-index:2;margin:0;padding:12px 16px;background:var(--ct-surface);color:var(--ct-accent,#f5bd41);font-size:13px;line-height:1.6}
.amap-shell{position:relative;border:1px solid var(--ct-border);border-radius:18px;overflow:hidden;background:var(--ct-surface);min-height:440px}.map-canvas{width:100%;height:440px}.compact .map-canvas{height:440px}.map-state{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:12px;padding:28px;color:var(--ct-text-muted);text-align:center;background:var(--ct-bg-soft)}.map-state strong{font-size:23px;color:var(--ct-text)}.map-search{display:flex;gap:8px;padding:12px}.map-search input{min-width:0;flex:1;padding:10px;border:1px solid var(--ct-border);border-radius:8px;background:var(--ct-bg);color:var(--ct-text)}.map-info{padding:14px;line-height:1.6;color:var(--ct-text-muted)}.poi-results{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}.poi-results button{padding:8px;border:1px solid var(--ct-border);border-radius:8px;background:var(--ct-bg);color:var(--ct-text);text-align:left;cursor:pointer}.poi-results small{display:block}.compact .poi-results{max-height:100px;overflow:auto}@media(max-width:620px){.map-canvas,.compact .map-canvas{height:340px}.amap-shell{min-height:340px}}
</style>
