<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api, ApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'
import { useAuthStore } from '../../stores/auth'

const route = useRoute()
const auth = useAuthStore()
const item = ref<Record<string, any> | null>(null)
const error = ref('')
const favoriteMessage = ref('')
const favoriteBusy = ref(false)
const closeBusy = ref(false)
onMounted(async () => {
  try { const response = await api<{ data: Record<string, any> }>(`/items/${route.params.id}/`); item.value = response.data }
  catch (reason) { error.value = reason instanceof ApiError ? reason.message : '无法读取物品详情' }
})
async function favorite(){if(!item.value)return;favoriteBusy.value=true;favoriteMessage.value='';try{await api('/items/favorites/',{method:'POST',body:JSON.stringify({item_id:item.value.id})});favoriteMessage.value='已收藏，可在个人中心追踪'}catch(reason){favoriteMessage.value=reason instanceof ApiError?reason.message:'收藏失败'}finally{favoriteBusy.value=false}}
async function closeItem(){if(!item.value)return;closeBusy.value=true;favoriteMessage.value='';try{const response=await api<{data:Record<string,any>}>(`/items/${item.value.id}/close/`,{method:'POST'});item.value=response.data;favoriteMessage.value='线索已关闭，不再进入开放候选'}catch(reason){favoriteMessage.value=reason instanceof ApiError?reason.message:'关闭失败'}finally{closeBusy.value=false}}
</script>

<template>
  <div class="page detail-page">
    <p v-if="error" class="panel error-box">{{ error }}</p>
    <div v-else-if="!item" class="panel loading">正在核对公开信息…</div>
    <template v-else>
      <nav class="breadcrumbs"><RouterLink :to="item.kind === 'LOST' ? '/lost' : '/found'">{{ item.kind === 'LOST' ? '遗失广场' : '招领广场' }}</RouterLink><AppIcon name="arrow" />{{ item.title }}</nav>
      <section class="detail-grid">
        <div class="item-gallery panel"><AppIcon name="box" /><p>图片仅用于展示与人工核验<br />本版不声称具备图像识别能力</p></div>
        <article class="detail-content"><div class="cluster"><span class="status-tag">{{ item.review_status }}</span><span class="status-tag">{{ item.business_status }}</span></div><h1>{{ item.title }}</h1><p class="description">{{ item.description }}</p><dl><div><dt>类别</dt><dd>{{ item.category_name }}</dd></div><div><dt>颜色 / 品牌</dt><dd>{{ [item.color, item.brand].filter(Boolean).join(' · ') || '未提供' }}</dd></div><div><dt>时间</dt><dd>{{ new Date(item.occurred_at).toLocaleString('zh-CN') }}</dd></div><div><dt>公开地点</dt><dd>{{ item.location_name }}</dd></div></dl><div class="privacy-note"><AppIcon name="shield" /><span><strong>隐私保护</strong>精确位置与核验答案不会公开。高匹配分也不能自动认定所有权。</span></div><p v-if="favoriteMessage" class="favorite-message">{{favoriteMessage}}</p><div class="actions"><button v-if="auth.user" class="button button-ghost" :disabled="favoriteBusy" @click="favorite"><AppIcon name="bell"/>{{favoriteBusy?'收藏中…':'收藏线索'}}</button><button v-if="item.allowed_actions?.includes('close')" class="button button-ghost danger" :disabled="closeBusy" @click="closeItem">{{closeBusy?'关闭中…':'关闭线索'}}</button><RouterLink v-if="item.kind === 'FOUND' && item.business_status === 'OPEN'" class="button button-brand" :to="`/claims/new/${item.id}`">发起认领核验 <AppIcon name="arrow" /></RouterLink></div></article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.breadcrumbs { display: flex; align-items: center; gap: 8px; margin-bottom: 26px; color: var(--ct-text-muted); font-size: 13px; }
.detail-grid { display: grid; grid-template-columns: 1.1fr .9fr; gap: 50px; }
.item-gallery { display: grid; place-items: center; align-content: center; min-height: 520px; color: var(--ct-brand); background: radial-gradient(circle, rgba(98,180,255,.17), transparent 45%), var(--ct-surface); font-size: 120px; }
.item-gallery p { color: var(--ct-text-muted); font-size: 12px; line-height: 1.7; text-align: center; }
.detail-content h1 { margin: 22px 0 14px; font-size: clamp(34px, 5vw, 54px); }
.description { color: var(--ct-text-muted); font-size: 16px; line-height: 1.9; }
.detail-content dl { margin: 30px 0; border-top: 1px solid var(--ct-border); }
.detail-content dl div { display: grid; grid-template-columns: 120px 1fr; padding: 16px 0; border-bottom: 1px solid var(--ct-border); }
.detail-content dt { color: var(--ct-text-muted); }
.detail-content dd { margin: 0; }
.privacy-note { display: flex; gap: 13px; padding: 16px; color: var(--ct-info); border: 1px solid rgba(98,180,255,.22); border-radius: 14px; background: rgba(98,180,255,.06); }
.privacy-note span { color: var(--ct-text-muted); font-size: 13px; line-height: 1.6; }.privacy-note strong { display: block; color: var(--ct-info); }
.actions{display:flex;gap:10px;margin-top:18px}.actions .button{flex:1}.actions .danger{color:var(--ct-danger)}.favorite-message{padding:10px;color:var(--ct-success);background:rgba(82,211,154,.06);border-radius:9px}
.loading,.error-box { padding: 80px; text-align: center; }.error-box { color: var(--ct-danger); }
@media (max-width: 800px) { .detail-grid { grid-template-columns: 1fr; gap: 30px; } .item-gallery { min-height: 320px; } }
</style>
