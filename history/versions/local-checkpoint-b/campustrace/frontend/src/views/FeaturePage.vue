<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'

const route = useRoute()
const pageId = computed(() => String(route.meta.pageId ?? ''))
const title = computed(() => String(route.meta.title ?? '功能页面'))
const description = computed(() => String(route.meta.description ?? ''))
const isAdmin = computed(() => pageId.value.startsWith('B'))
const guidance = computed(() => {
  if (pageId.value === 'P27') return ['发布前删除联系方式和完整证件号码', '匹配分只代表线索相似程度', '认领需要举证、人工核验和安全交接']
  if (pageId.value === 'P13' || pageId.value === 'P14') return ['查看开放状态和营业时间', '按保管站点办理认领', '线下交接前先在系统完成预约']
  if (isAdmin.value) return ['所有管理写操作必须记录审计日志', '站点协调员只能处理授权站点数据', '批量任务刷新后仍可从任务 ID 恢复']
  return ['数据由后端权限范围决定', '审核状态和业务状态分开呈现', '无权对象以 403/404 策略阻止枚举']
})
</script>

<template>
  <div class="page feature-page">
    <header><p class="eyebrow">{{ pageId }} · {{ isAdmin ? 'OPERATIONS' : 'CAMPUS SERVICE' }}</p><h1 class="page-title">{{ title }}</h1><p class="page-lead">{{ description }}</p></header>
    <div class="feature-layout">
      <section class="panel workspace">
        <div class="workspace-top"><div><span class="status-tag">接口联调中</span><h2>该路由已纳入页面合同</h2></div><AppIcon :name="isAdmin ? 'shield' : 'spark'" /></div>
        <p>当前阶段已完成路由、角色守卫、视觉框架与领域合同。此页面的专属数据表格/表单尚未通过端到端证据验收，因此不会展示随机统计或伪造的“已完成”状态。</p>
        <div class="skeleton-table" aria-label="待接入真实数据的结构预览"><div v-for="index in 4" :key="index"><span></span><span></span><span></span></div></div>
      </section>
      <aside class="panel guide"><p class="eyebrow">SAFETY CONTRACT</p><h2>本页约束</h2><ul><li v-for="item in guidance" :key="item"><AppIcon name="shield" /><span>{{ item }}</span></li></ul><RouterLink class="button button-ghost" :to="isAdmin ? '/admin/overview' : '/home'">返回{{ isAdmin ? '运营总览' : '首页' }}</RouterLink></aside>
    </div>
  </div>
</template>

<style scoped>
.feature-layout{display:grid;grid-template-columns:1fr 340px;gap:18px;margin-top:36px}.workspace,.guide{padding:28px;box-shadow:none}.workspace-top{display:flex;justify-content:space-between;align-items:start}.workspace-top>svg{color:var(--ct-brand);font-size:42px}.workspace h2{margin:18px 0 0}.workspace>p{max-width:700px;color:var(--ct-text-muted);line-height:1.8}.skeleton-table{overflow:hidden;margin-top:28px;border:1px solid var(--ct-border);border-radius:13px}.skeleton-table div{display:grid;grid-template-columns:1.4fr .8fr .5fr;gap:30px;padding:18px}.skeleton-table div+div{border-top:1px solid var(--ct-border)}.skeleton-table span{height:9px;background:linear-gradient(90deg,var(--ct-bg-soft),var(--ct-surface-raised));border-radius:9px}.guide h2{margin:15px 0 20px}.guide ul{display:grid;gap:15px;margin:0 0 26px;padding:0;list-style:none}.guide li{display:flex;gap:10px;color:var(--ct-text-muted);line-height:1.55}.guide li svg{flex:0 0 auto;color:var(--ct-success)}@media(max-width:850px){.feature-layout{grid-template-columns:1fr}}
</style>
