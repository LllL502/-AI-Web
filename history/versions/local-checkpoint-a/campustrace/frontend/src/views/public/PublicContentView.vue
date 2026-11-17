<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api, ApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'
const props=defineProps<{kind:'help'|'stories'}>()
type Entry={id:number;title:string;slug:string;body:string;category?:string;related_item_title?:string;published_at:string}
const entries=ref<Entry[]>([]);const loading=ref(true);const error=ref('')
const title=computed(()=>props.kind==='help'?'帮助中心':'找回故事')
async function load(){loading.value=true;error.value='';try{const response=await api<{data:{items:Entry[]}}>(`/content/${props.kind}/?page_size=100`);entries.value=response.data.items}catch(reason){error.value=reason instanceof ApiError?reason.message:'无法读取内容'}finally{loading.value=false}}
onMounted(load);watch(()=>props.kind,load)
</script>
<template><div class="page content-page"><header><h1 class="page-title">{{title}}</h1><p class="page-lead">{{kind==='help'?'了解发布、审核、匹配、认领、隐私和安全交接流程。':'只展示已记录当事人授权的内容；演示故事会明确标注合成来源。'}}</p></header><p v-if="loading" class="empty">正在读取已发布内容…</p><p v-else-if="error" class="empty error">{{error}}</p><section v-else-if="entries.length" :class="kind==='help'?'help-list':'story-grid'"><article v-for="(entry,index) in entries" :key="entry.id" class="panel entry"><span class="number">{{String(index+1).padStart(2,'0')}}</span><div><p class="eyebrow">{{entry.category||'授权故事'}}</p><h2>{{entry.title}}</h2><p>{{entry.body}}</p><small v-if="entry.related_item_title">相关物品：{{entry.related_item_title}}</small><time v-if="entry.published_at">{{new Date(entry.published_at).toLocaleDateString('zh-CN')}}</time></div><AppIcon name="spark"/></article></section><div v-else class="empty"><AppIcon name="box"/><h2>尚无已发布内容</h2><p>暂时还没有可展示内容。</p></div></div></template>
<style scoped>.help-list,.story-grid{display:grid;gap:14px;margin-top:36px}.story-grid{grid-template-columns:repeat(2,1fr)}.entry{display:grid;grid-template-columns:auto 1fr auto;gap:20px;padding:26px;box-shadow:none}.number{color:var(--ct-brand);font:700 24px Georgia,serif}.entry h2{margin:9px 0}.entry div>p:not(.eyebrow){color:var(--ct-text-muted);line-height:1.8}.entry small,.entry time{display:block;margin-top:10px;color:var(--ct-text-muted)}.entry>svg{color:var(--ct-brand);font-size:27px}.empty{display:grid;place-items:center;gap:8px;min-height:300px;color:var(--ct-text-muted);border:1px dashed var(--ct-border);border-radius:16px}.error{color:var(--ct-danger)}@media(max-width:760px){.story-grid{grid-template-columns:1fr}}</style>
