<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api, ApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'
import AMapCampus from '../../components/AMapCampus.vue'

type Layer='ALL'|'LOST'|'FOUND'
type LocationCount={id:number;name:string;count:number}
const layerOptions:Layer[]=['ALL','LOST','FOUND']
const active=ref('请选择一个校园热点');const layer=ref<Layer>('ALL');const locations=ref<LocationCount[]>([]);const total=ref(0);const loading=ref(true);const error=ref('')
const hotspots=computed(()=>locations.value.slice(0,6).map(entry=>({label:entry.name,count:entry.count})))
const areas=computed(()=>hotspots.value.map(entry=>`${entry.label} · ${entry.count} 条公开线索`))
async function load(){loading.value=true;error.value='';try{const suffix=layer.value==='ALL'?'':`?kind=${layer.value}`;const response=await api<{data:{total:number;locations:LocationCount[]}}>(`/items/map-summary/${suffix}`);locations.value=response.data.locations;total.value=response.data.total;active.value=areas.value[0]??'当前图层暂无公开线索'}catch(reason){error.value=reason instanceof ApiError?reason.message:'热点数据加载失败'}finally{loading.value=false}}
onMounted(load);watch(layer,load)
</script>

<template><div class="page map-page"><header class="map-header"><div><p class="eyebrow"><AppIcon name="map"/> P12 · 线索空间分布</p><h1 class="page-title">校园线索地图</h1><p class="page-lead">在真实底图中搜索校园地点。右侧统计仅展示当前校区的公开区域，不公开物品精确标点。</p></div><div class="layer-control" aria-label="线索图层"><button v-for="option in layerOptions" :key="option" :class="{active:layer===option}" @click="layer=option">{{{ALL:'全部',LOST:'遗失',FOUND:'招领'}[option]}}</button></div></header><div class="map-layout"><AMapCampus/><aside class="panel area-panel"><p v-if="loading">正在聚合公开线索…</p><p v-else-if="error" class="error">{{error}}</p><template v-else><span class="status-tag">{{layer==='ALL'?'全部图层':layer==='LOST'?'遗失图层':'招领图层'}} · {{total}} 条</span><h2>{{active}}</h2><p>公开线索按区域统计。地图中的搜索候选需核对，尚未确认的地点不作为服务站。</p><ol><li v-for="(area,index) in areas" :key="area"><button type="button" @click="active=area"><span>{{String(index+1).padStart(2,'0')}}</span>{{area}}</button></li></ol></template></aside></div></div></template>

<style scoped>.map-header{display:flex;justify-content:space-between;align-items:end;gap:30px;margin-bottom:32px}.layer-control{display:flex;padding:4px;border:1px solid var(--ct-border);border-radius:12px;background:var(--ct-surface)}.layer-control button{padding:9px 14px;color:var(--ct-text-muted);border:0;border-radius:8px;background:transparent;cursor:pointer}.layer-control button.active{color:var(--ct-brand-ink);background:var(--ct-brand)}.map-layout{display:grid;grid-template-columns:1fr 340px;gap:18px}.area-panel{padding:24px;box-shadow:none}.area-panel h2{margin:22px 0 10px;font-size:22px}.area-panel p{color:var(--ct-text-muted);line-height:1.7}.area-panel ol{margin:22px 0 0;padding:0;list-style:none}.area-panel li+li{border-top:1px solid var(--ct-border)}.area-panel button{display:flex;width:100%;gap:12px;padding:14px 0;color:var(--ct-text);border:0;background:transparent;text-align:left;cursor:pointer}.area-panel button span{color:var(--ct-brand)}.state{display:grid;place-items:center;min-height:430px;color:var(--ct-text-muted)}.error{color:var(--ct-danger)}@media(max-width:900px){.map-header{align-items:start;flex-direction:column}.map-layout{grid-template-columns:1fr}}</style>
