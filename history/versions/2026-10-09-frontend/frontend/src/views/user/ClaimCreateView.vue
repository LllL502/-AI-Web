<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, ApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'

const route = useRoute(); const router = useRouter()
const form = reactive({ statement: '', related_lost_item_id: '', private_feature: '', possession_detail: '' })
const busy = ref(false); const error = ref('')
async function submit() {
  busy.value = true; error.value = ''
  try {
    const response = await api<{ data: { id: string } }>('/claims/', { method: 'POST', body: JSON.stringify({ found_item_id: route.params.foundId, related_lost_item_id: form.related_lost_item_id || null, statement: form.statement, evidence: { private_feature: form.private_feature, possession_detail: form.possession_detail } }) })
    await router.push(`/claims/${response.data.id}`)
  } catch (reason) { error.value = reason instanceof ApiError ? reason.message : '提交失败' }
  finally { busy.value = false }
}
</script>

<template><div class="page claim-page"><header><p class="eyebrow">P15 · PRIVACY-PRESERVING CLAIM</p><h1 class="page-title">发起认领核验</h1><p class="page-lead">请提供只有真实所有者更可能知道的特征。证据仅用于授权核验，不进入公开匹配索引。</p></header><form class="panel claim-form" @submit.prevent="submit"><div class="safety"><AppIcon name="shield" /><div><strong>先核验，再交接</strong><p>不要填写支付密码、身份证完整号码或与物品无关的敏感信息。</p></div></div><label><span>关联我的遗失信息 ID（可选）</span><input v-model="form.related_lost_item_id" placeholder="用于串联你已发布的遗失信息" /></label><label><span>认领说明</span><textarea v-model="form.statement" required rows="5" maxlength="3000" placeholder="说明遗失经过，以及公开信息未覆盖的识别依据。"></textarea></label><label><span>私密外观特征</span><input v-model="form.private_feature" required placeholder="例如：保护壳内侧的小划痕位置" /></label><label><span>持有证明</span><textarea v-model="form.possession_detail" required rows="4" placeholder="例如：购买记录类型、可现场解锁的能力；不要粘贴完整账号信息。"></textarea></label><label class="consent"><input required type="checkbox" />我理解高匹配分不等于所有权，愿意由站点协调员人工核验并遵守安全交接流程。</label><p v-if="error" class="error">{{ error }}</p><footer><button class="button button-brand" :disabled="busy">{{ busy ? '正在加密提交…' : '提交认领申请' }} <AppIcon name="arrow" /></button></footer></form></div></template>

<style scoped>
.claim-page { max-width: 860px; }.claim-form { display: grid; gap: 20px; margin-top: 34px; padding: 32px; }.claim-form label > span { display: block; margin-bottom: 8px; color: var(--ct-text-muted); font-size: 13px; }.claim-form input,.claim-form textarea { width: 100%; padding: 13px; color: var(--ct-text); border: 1px solid var(--ct-border); border-radius: 11px; background: var(--ct-bg-soft); }.safety { display: flex; gap: 14px; padding: 16px; color: var(--ct-success); border: 1px solid rgba(82,211,154,.25); border-radius: 13px; background: rgba(82,211,154,.06); }.safety p { margin: 4px 0 0; color: var(--ct-text-muted); }.consent { display: flex; gap: 10px; color: var(--ct-text-muted); line-height: 1.6; }.consent input { width: auto; }.claim-form footer { display: flex; justify-content: flex-end; }.error { color: var(--ct-danger); }
</style>
