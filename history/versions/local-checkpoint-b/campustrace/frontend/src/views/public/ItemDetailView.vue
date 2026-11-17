<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api, ApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'
import ItemVisual from '../../components/ItemVisual.vue'
import { useAuthStore } from '../../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const item = ref<Record<string, any> | null>(null)
const error = ref('')
const favoriteMessage = ref('')
const favoriteBusy = ref(false)
const closeBusy = ref(false)
const manageBusy = ref(false)
const selectedImage = ref('')
const mediaUrls = computed(() => {
  const values = Array.isArray(item.value?.media) ? item.value.media : []
  return values.map((entry: Record<string, any>) => entry.thumbnail || entry.file).filter(Boolean)
})
const activeImageUrl = computed(() => selectedImage.value || mediaUrls.value[0] || item.value?.image_url || '')
onMounted(async () => {
  try { const response = await api<{ data: Record<string, any> }>(`/items/${route.params.id}/`); item.value = response.data }
  catch (reason) { error.value = reason instanceof ApiError ? reason.message : '无法读取物品详情' }
})
async function favorite(){if(!item.value)return;favoriteBusy.value=true;favoriteMessage.value='';try{await api('/items/favorites/',{method:'POST',body:JSON.stringify({item_id:item.value.id})});favoriteMessage.value='已收藏，可在个人中心追踪'}catch(reason){favoriteMessage.value=reason instanceof ApiError?reason.message:'收藏失败'}finally{favoriteBusy.value=false}}
async function closeItem(){if(!item.value)return;closeBusy.value=true;favoriteMessage.value='';try{const response=await api<{data:Record<string,any>}>(`/items/${item.value.id}/close/`,{method:'POST'});item.value=response.data;favoriteMessage.value='线索已关闭，不再进入开放候选'}catch(reason){favoriteMessage.value=reason instanceof ApiError?reason.message:'关闭失败'}finally{closeBusy.value=false}}
async function withdrawItem(){if(!item.value||!window.confirm('确认撤回待审核信息并恢复为草稿吗？'))return;manageBusy.value=true;favoriteMessage.value='';try{const response=await api<{data:Record<string,any>}>(`/items/${item.value.id}/withdraw/`,{method:'POST'});item.value=response.data;favoriteMessage.value='已撤回为草稿，现在可以继续编辑'}catch(reason){favoriteMessage.value=reason instanceof ApiError?reason.message:'撤回失败'}finally{manageBusy.value=false}}
async function deleteItem(){if(!item.value||!window.confirm('确认永久删除这条发布信息吗？删除后将同时从对应广场移除，此操作不可撤销。'))return;manageBusy.value=true;favoriteMessage.value='';try{await api(`/items/${item.value.id}/`,{method:'DELETE'});await router.push('/me/items')}catch(reason){favoriteMessage.value=reason instanceof ApiError?reason.message:'删除失败';manageBusy.value=false}}
</script>

<template>
  <div class="page detail-page">
    <p v-if="error" class="panel error-box">{{ error }}</p>
    <div v-else-if="!item" class="panel loading">正在核对公开信息…</div>
    <template v-else>
      <nav class="breadcrumbs"><RouterLink :to="item.kind === 'LOST' ? '/lost' : '/found'">{{ item.kind === 'LOST' ? '遗失广场' : '招领广场' }}</RouterLink><AppIcon name="arrow" />{{ item.title }}</nav>
      <section class="detail-grid">
        <div class="item-gallery panel"><ItemVisual :title="item.title" :category="item.category_name" :color="item.color" :image-url="activeImageUrl" variant="detail" /><div v-if="mediaUrls.length > 1" class="media-thumbnails" aria-label="物品照片"><button v-for="(url,index) in mediaUrls" :key="url" type="button" :class="{active:activeImageUrl===url}" :aria-label="`查看第${index+1}张照片`" @click="selectedImage=url"><img :src="url" alt=""/></button></div></div>
        <article class="detail-content"><div class="cluster"><span class="status-tag">{{ item.review_status }}</span><span class="status-tag">{{ item.business_status }}</span></div><h1>{{ item.title }}</h1><p class="description">{{ item.description }}</p><dl><div><dt>类别</dt><dd>{{ item.category_name }}</dd></div><div><dt>颜色 / 品牌</dt><dd>{{ [item.color, item.brand].filter(Boolean).join(' · ') || '未提供' }}</dd></div><div><dt>时间</dt><dd>{{ new Date(item.occurred_at).toLocaleString('zh-CN') }}</dd></div><div><dt>公开地点</dt><dd>{{ item.location_name }}</dd></div><div v-if="item.kind === 'FOUND'"><dt>保管方式</dt><dd>{{ item.station_name || '拾取者暂存' }}</dd></div></dl><div class="privacy-badge"><AppIcon name="shield" /><strong>隐私保护</strong></div><p v-if="favoriteMessage" class="favorite-message">{{favoriteMessage}}</p><div class="actions"><RouterLink v-if="item.allowed_actions?.includes('edit')" class="button button-ghost" :to="`/items/${item.id}/edit`">编辑线索</RouterLink><button v-if="item.allowed_actions?.includes('withdraw')" class="button button-ghost" :disabled="manageBusy" @click="withdrawItem">撤回审核</button><button v-if="item.allowed_actions?.includes('delete')" class="button button-ghost danger" :disabled="manageBusy" @click="deleteItem">删除发布</button><button v-if="auth.user" class="button button-ghost" :disabled="favoriteBusy" @click="favorite"><AppIcon name="bell"/>{{favoriteBusy?'收藏中…':'收藏线索'}}</button><button v-if="item.allowed_actions?.includes('close')" class="button button-ghost danger" :disabled="closeBusy" @click="closeItem">{{closeBusy?'关闭中…':'关闭线索'}}</button><RouterLink v-if="item.allowed_actions?.includes('claim')" class="button button-brand" :to="`/claims/new/${item.id}`">申请认领 <AppIcon name="arrow" /></RouterLink></div></article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.breadcrumbs { display: flex; align-items: center; gap: 8px; margin-bottom: 26px; color: var(--ct-text-muted); font-size: 13px; }
.detail-grid { display: grid; grid-template-columns: 1.1fr .9fr; gap: 50px; }
.item-gallery { overflow: hidden; }
.media-thumbnails{display:flex;gap:9px;overflow:auto;padding:12px}.media-thumbnails button{flex:0 0 76px;height:62px;padding:0;overflow:hidden;border:2px solid transparent;border-radius:8px;background:var(--ct-bg-soft);cursor:pointer}.media-thumbnails button.active{border-color:var(--ct-brand)}.media-thumbnails img{display:block;width:100%;height:100%;object-fit:cover}
.item-gallery p { color: var(--ct-text-muted); font-size: 12px; line-height: 1.7; text-align: center; }
.detail-content h1 { margin: 22px 0 14px; font-size: clamp(34px, 5vw, 54px); }
.description { color: var(--ct-text-muted); font-size: 16px; line-height: 1.9; }
.detail-content dl { margin: 30px 0; border-top: 1px solid var(--ct-border); }
.detail-content dl div { display: grid; grid-template-columns: 120px 1fr; padding: 16px 0; border-bottom: 1px solid var(--ct-border); }
.detail-content dt { color: var(--ct-text-muted); }
.detail-content dd { margin: 0; }
.privacy-badge { display: inline-flex; align-items: center; gap: 8px; padding: 9px 12px; color: var(--ct-info); border: 1px solid rgba(40,92,75,.22); border-radius: 999px; background: rgba(40,92,75,.06); }
.actions{display:flex;gap:10px;margin-top:18px}.actions .button{flex:1}.actions .danger{color:var(--ct-danger)}.favorite-message{padding:10px;color:var(--ct-success);background:rgba(54,100,75,.06);border-radius:9px}
.loading,.error-box { padding: 80px; text-align: center; }.error-box { color: var(--ct-danger); }
@media (max-width: 800px) { .detail-grid { grid-template-columns: 1fr; gap: 30px; } .item-gallery { min-height: 320px; } }
</style>
