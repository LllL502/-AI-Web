<script setup lang="ts">
import {readableApiError} from '../../api/client'
import {statusLabel} from '../../utils/statusLabels'
import ListPager from '../../components/ListPager.vue'
import {useListPage} from '../../composables/useListPage'
import {apiCollection} from '../../api/collections'
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'
type Station={id:number;name:string;location:{name:string};address:string;opening_hours:Record<string,string>;capacity:number;status:string}
const stations=ref<Station[]>([]),loading=ref(true),error=ref('')
onMounted(async()=>{try{const response=await apiCollection<{data:{items:Station[]}}>('/stations/?page_size=100');stations.value=response.data.items}catch(reason){error.value=readableApiError(reason,'无法读取服务站')}finally{loading.value=false}})

const {page:pagedStationsPage,rows:pagedStations}=useListPage(stations)
</script>
<template><div class="page"><header><h1 class="page-title">校园服务站</h1><p class="page-lead">只展示经学校授权、平台核验的官方站点。线下交接前需先完成认领批准与预约。</p></header><p v-if="loading" class="empty">正在读取站点…</p><p v-else-if="error" class="empty error">{{error}}</p><section v-else-if="stations.length" class="station-grid"><RouterLink v-for="station in pagedStations" :key="station.id" :to="`/stations/${station.id}`" class="panel station"><div class="station-icon"><AppIcon name="map"/></div><span class="status-tag">官方已核验 · {{statusLabel(station.status)}}</span><h2>{{station.name}}</h2><p>{{station.location.name}} · {{station.address}}</p><dl><div><dt>工作日</dt><dd>{{station.opening_hours.weekdays??'未公布'}}</dd></div><div><dt>保管容量</dt><dd>{{station.capacity}}</dd></div></dl><footer>查看站点详情 <AppIcon name="arrow"/></footer></RouterLink></section><section v-else class="empty-state panel"><AppIcon name="map"/><h2>当前校区暂未开通官方服务站</h2><p>拾取者仍可暂存物品，认领通过后双方可约定图书馆门口等公共地点直接交接。这些只是见面地点，不承担物品保管和工作人员核验。</p><RouterLink class="button button-brand" to="/stations/apply">申请学校官方接入</RouterLink></section><ListPager :page="pagedStationsPage" :total="stations.length" @change="pagedStationsPage=$event"/></div></template>
<style scoped>.station-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:18px;margin-top:36px}.station{position:relative;padding:26px;box-shadow:none}.station-icon{display:grid;place-items:center;width:50px;aspect-ratio:1;color:var(--ct-brand);border:1px solid var(--ct-border-strong);border-radius:14px;background:#8d302e0f;font-size:25px}.station>.status-tag{position:absolute;top:26px;right:26px}.station h2{margin:24px 0 7px}.station p,.empty-state p{color:var(--ct-text-muted);line-height:1.7}dl{display:grid;grid-template-columns:1fr 1fr;gap:1px;margin:22px 0;background:var(--ct-border)}dl div{padding:13px;background:var(--ct-bg-soft)}dt{color:var(--ct-text-muted);font-size:11px}dd{margin:4px 0 0}footer{display:flex;justify-content:space-between;color:var(--ct-brand)}.empty{display:grid;place-items:center;min-height:300px}.empty-state{display:grid;place-items:center;gap:12px;margin-top:34px;padding:45px;text-align:center}.empty-state>svg{color:var(--ct-brand);font-size:40px}.empty-state p{max-width:760px}.error{color:var(--ct-danger)}@media(max-width:680px){.station-grid{grid-template-columns:1fr}}</style>
