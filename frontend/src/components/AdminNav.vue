<script setup lang="ts">
import {RouterLink} from 'vue-router'
import {computed} from 'vue'
import {useAuthStore} from '../stores/auth'
const auth=useAuthStore()
const links=[['/admin/overview','总览',true],['/admin/reviews','内容审核',true],['/admin/items','物品管理',true],['/admin/claims','认领管理',true],['/admin/users','用户管理',false],['/admin/stations','站点管理',false],['/admin/dictionaries','类别与地点',false],['/admin/matching/config','匹配参数',false],['/admin/matching/lab','算法评测',false],['/admin/reports','报表',true],['/admin/content','帮助内容',false],['/admin/system','系统状态',false]] as const
const visible=computed(()=>links.filter(row=>row[2]||auth.user?.role==='ADMIN'))
</script>
<template><nav class="admin-nav" aria-label="运营管理导航"><RouterLink v-for="[path,label] in visible" :key="path" :to="path">{{label}}</RouterLink></nav></template>
<style scoped>.admin-nav{display:flex;flex-wrap:wrap;gap:8px;margin:20px auto 0;max-width:1400px;padding:0 24px}.admin-nav a{padding:9px 13px;border-radius:9px;border:1px solid var(--ct-border);font-size:14px;background:white;color:var(--ct-text-muted)}.admin-nav a.router-link-exact-active{background:var(--ct-brand);color:white;border-color:var(--ct-brand)}@media(max-width:620px){.admin-nav{padding:0 16px;gap:6px}.admin-nav a{font-size:13px;padding:8px 10px}}</style>