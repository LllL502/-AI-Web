<script setup lang="ts">
import {readableApiError} from '../../api/client'
import ListPager from '../../components/ListPager.vue'
import {useListPage} from '../../composables/useListPage'
import {apiCollection} from '../../api/collections'
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'
type Claim={id:string;item_title:string;status:string;submitted_at:string;updated_at:string;viewer_role:string;handover_method:string;appointment?:{station_id:number;scheduled_at:string};custody_station?:{name:string}|null;allowed_actions:string[]}
const claims=ref<Claim[]>([]);const filter=ref('ALL');const loading=ref(true);const error=ref('')
const visible=computed(()=>filter.value==='ALL'?claims.value:claims.value.filter(entry=>entry.status===filter.value))
function claimHint(claim:Claim){
  if(claim.viewer_role==='CLAIMANT'&&claim.status==='APPROVED'&&claim.custody_station)return `物品已在${claim.custody_station.name}，可领取`
  if(claim.viewer_role==='CLAIMANT'&&claim.status==='APPROVED')return '已通过，请选择交接方式'
  if(claim.viewer_role==='CLAIMANT'&&claim.status==='HANDOVER_PENDING'&&claim.handover_method==='STATION')return claim.custody_station?`可前往${claim.custody_station.name}领取`:'可前往服务站交接'
  return claim.allowed_actions.length?'待处理':''
}
onMounted(async()=>{try{const response=await apiCollection<{data:{items:Claim[]}}>('/claims/?page_size=100');claims.value=response.data.items}catch(reason){error.value=readableApiError(reason,'无法读取认领记录')}finally{loading.value=false}})
async function removeClaim(claim:Claim){
  if(!window.confirm(`确定从“我的认领”中删除“${claim.item_title}”吗？`))return
  try{await api(`/claims/${claim.id}/mine/`,{method:'DELETE'});claims.value=claims.value.filter(entry=>entry.id!==claim.id)}catch(reason){error.value=readableApiError(reason,'删除失败')}
}

const {page:pagedClaimsPage,rows:pagedClaims}=useListPage(visible)
</script>
<template><div class="page"><header><h1 class="page-title">认领记录</h1></header><div class="tabs"><button v-for="entry in [['ALL','全部'],['SUBMITTED','待核对'],['NEEDS_INFO','待补充'],['APPROVED','已通过'],['HANDOVER_PENDING','待交接'],['COMPLETED','已完成']]" :key="entry[0]" :class="{active:filter===entry[0]}" @click="filter=entry[0]">{{entry[1]}}</button></div><p v-if="loading" class="empty">正在读取…</p><p v-else-if="error" class="empty error">{{error}}</p><div v-else-if="visible.length" class="claim-list"><article v-for="claim in pagedClaims" :key="claim.id" class="panel claim"><span class="status-tag">{{claim.viewer_role==='CLAIMANT'?'我的申请':'收到的申请'}}</span><RouterLink :to="`/claims/${claim.id}`" class="claim-main"><h2>{{claim.item_title}}</h2><p>{{new Date(claim.updated_at).toLocaleString('zh-CN')}}</p></RouterLink><span v-if="claimHint(claim)" class="todo">{{claimHint(claim)}}</span><button v-if="claim.viewer_role==='CLAIMANT'" class="delete-button" type="button" @click="removeClaim(claim)">删除</button><RouterLink :to="`/claims/${claim.id}`" aria-label="查看认领详情"><AppIcon name="arrow"/></RouterLink></article></div><div v-else class="empty"><AppIcon name="shield"/><h2>当前没有记录</h2><RouterLink to="/found" class="button button-brand">浏览招领线索</RouterLink></div><ListPager :page="pagedClaimsPage" :total="visible.length" @change="pagedClaimsPage=$event"/></div></template>
<style scoped>.tabs{display:flex;gap:7px;overflow:auto;margin:32px 0 20px}.tabs button{white-space:nowrap;padding:10px 14px;color:var(--ct-text-muted);border:1px solid var(--ct-border);border-radius:10px;background:transparent}.tabs button.active{color:var(--ct-brand-ink);background:var(--ct-brand)}.claim-list{display:grid;gap:10px}.claim{display:grid;grid-template-columns:auto 1fr auto auto auto;gap:18px;align-items:center;padding:19px;box-shadow:none}.claim-main{color:inherit;text-decoration:none}.claim h2,.claim p{margin:0}.claim p{margin-top:5px;color:var(--ct-text-muted);font-size:12px}.todo{color:var(--ct-brand);font-size:12px}.delete-button{padding:7px 10px;color:var(--ct-danger);border:1px solid var(--ct-border-strong);border-radius:8px;background:transparent;cursor:pointer}.delete-button:hover{background:rgba(173,52,52,.07)}.empty{display:grid;place-items:center;gap:12px;min-height:280px;color:var(--ct-text-muted);border:1px dashed var(--ct-border);border-radius:16px}.error{color:var(--ct-danger)}@media(max-width:650px){.claim{grid-template-columns:auto 1fr auto}.claim>.todo{grid-column:2}.delete-button{grid-column:3}}</style>
