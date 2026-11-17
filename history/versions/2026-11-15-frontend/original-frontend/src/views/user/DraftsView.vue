<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, ApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'
type Item={id:string;title:string;kind:string;review_status:string;business_status:string;updated_at:string;allowed_actions:string[]}
const items=ref<Item[]>([]);const filter=ref('ALL');const loading=ref(true);const error=ref('');const success=ref('');const busy=ref('')
const visible=computed(()=>filter.value==='ALL'?items.value:items.value.filter(item=>item.review_status===filter.value))
async function load(){try{const response=await api<{data:{items:Item[]}}>('/items/?mine=true&page_size=100');items.value=response.data.items.filter(item=>['DRAFT','PENDING','REJECTED'].includes(item.review_status))}catch(reason){error.value=reason instanceof ApiError?reason.message:'无法读取草稿'}finally{loading.value=false}}
async function act(item:Item,action:'submit'|'withdraw'|'delete'){
  const prompts={submit:'确认提交审核吗？',withdraw:'确认撤回并恢复为草稿吗？',delete:'确认永久删除这条未公开草稿吗？'}
  if(!window.confirm(prompts[action]))return
  busy.value=`${item.id}:${action}`;error.value='';success.value=''
  try{
    if(action==='delete')await api(`/items/${item.id}/`,{method:'DELETE'})
    else await api(`/items/${item.id}/${action}/`,{method:'POST'})
    success.value=action==='delete'?'草稿已删除':action==='withdraw'?'已撤回为草稿':'已提交审核'
    await load()
  }catch(reason){error.value=reason instanceof ApiError?reason.message:'操作失败'}finally{busy.value=''}
}
onMounted(load)
</script>
<template><div class="page"><header><h1 class="page-title">草稿与审核进度</h1><p class="page-lead">未通过审核的内容只对你和有权协调员可见，不进入公开搜索和匹配索引。</p></header><div class="tabs"><button v-for="entry in [['ALL','全部'],['DRAFT','草稿'],['PENDING','待审'],['REJECTED','被驳回']]" :key="entry[0]" :class="{active:filter===entry[0]}" @click="filter=entry[0]">{{entry[1]}}</button></div><p v-if="success" class="notice success">{{success}}</p><p v-if="error" class="notice error">{{error}}</p><p v-if="loading" class="empty">正在读取你的非公开内容…</p><div v-else-if="visible.length" class="draft-list"><article v-for="item in visible" :key="item.id" class="panel draft"><span class="kind">{{item.kind==='LOST'?'遗失':'招领'}}</span><div><h2>{{item.title}}</h2><p>更新于 {{new Date(item.updated_at).toLocaleString('zh-CN')}}</p></div><span class="status-tag">{{item.review_status}}</span><div class="actions"><RouterLink class="button button-ghost" :to="`/items/${item.id}`">查看</RouterLink><RouterLink v-if="item.allowed_actions.includes('edit')" class="button button-ghost" :to="`/items/${item.id}/edit`">编辑</RouterLink><button v-if="item.allowed_actions.includes('submit')" class="button button-brand" :disabled="Boolean(busy)" @click="act(item,'submit')">提交审核</button><button v-if="item.allowed_actions.includes('withdraw')" class="button button-ghost" :disabled="Boolean(busy)" @click="act(item,'withdraw')">撤回</button><button v-if="item.allowed_actions.includes('delete')" class="button button-ghost danger" :disabled="Boolean(busy)" @click="act(item,'delete')">删除</button></div></article></div><div v-else class="empty"><AppIcon name="box"/><h2>当前分类没有内容</h2><RouterLink class="button button-brand" to="/publish/lost">新建遗失信息</RouterLink></div></div></template>
<style scoped>.tabs{display:flex;gap:8px;margin:32px 0 20px}.tabs button{padding:10px 16px;color:var(--ct-text-muted);border:1px solid var(--ct-border);border-radius:10px;background:transparent}.tabs button.active{color:var(--ct-brand-ink);background:var(--ct-brand)}.draft-list{display:grid;gap:12px}.draft{display:grid;grid-template-columns:auto minmax(180px,1fr) auto auto;gap:18px;align-items:center;padding:20px;box-shadow:none}.draft h2,.draft p{margin:0}.draft p{margin-top:6px;color:var(--ct-text-muted);font-size:12px}.kind{color:var(--ct-brand)}.actions{display:flex;gap:6px;flex-wrap:wrap}.danger{color:var(--ct-danger)}.empty{display:grid;place-items:center;gap:12px;min-height:260px;color:var(--ct-text-muted);border:1px dashed var(--ct-border);border-radius:16px}.notice{margin:0 0 12px;padding:12px;border-radius:10px}.error{color:var(--ct-danger);background:rgba(173,52,52,.07)}.success{color:var(--ct-success);background:rgba(54,100,75,.07)}@media(max-width:850px){.draft{grid-template-columns:auto 1fr}.draft>.status-tag,.draft>.actions{grid-column:2}.tabs{overflow:auto}}</style>
