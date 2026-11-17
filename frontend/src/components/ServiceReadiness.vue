<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {api,readableApiError} from '../api/client'
const models=ref<Record<string,{state:string;ready:boolean;busy?:boolean}>>({}),error=ref(''),busy=ref(false)
const names:Record<string,string>={extraction:'小寻对话',embedding:'语义检索',vision:'图片理解',voice:'小寻童声'}
const states:Record<string,string>={available:'已就绪',starting:'模型准备中',unavailable:'服务未启动',model_missing:'模型未就绪',not_configured:'未配置',not_probed:'未验证远程服务',simulated:'模拟模式'}
async function refresh(){busy.value=true;error.value='';try{models.value=(await api<{data:{models:typeof models.value}}>('/assistant/health/')).data.models}catch(reason){error.value=readableApiError(reason,'无法检查AI服务')}finally{busy.value=false}}
onMounted(refresh)
</script>
<template><section class="panel readiness"><header><h2>AI服务状态</h2><button class="button button-ghost" :disabled="busy" @click="refresh">检查状态</button></header><p v-if="error" role="alert">{{error}}</p><p v-if="busy&&!Object.keys(models).length">正在检查服务…</p><div class="services"><article v-for="(label,key) in names" :key="key"><strong>{{label}}</strong><span :class="{offline:models[key]&&!models[key].ready}">{{models[key]?.busy?'使用中':states[models[key]?.state??'']??'正在检查'}}</span></article></div></section></template>
<style scoped>.readiness{padding:24px;margin:24px 0}.readiness header{display:flex;justify-content:space-between;align-items:center;gap:16px}.services{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.services article{display:grid;gap:8px;padding:16px;border:1px solid var(--ct-border);border-radius:12px}.offline{color:var(--ct-danger)}@media(max-width:650px){.services{grid-template-columns:repeat(2,minmax(0,1fr))}}</style>
