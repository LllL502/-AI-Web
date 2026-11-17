<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api, ApiError } from '../../api/client'

type Item = {
  id: string
  kind: 'LOST' | 'FOUND'
  title: string
  category: number
  category_name: string
  station_name?: string | null
}

const route = useRoute()
const router = useRouter()
const foundItem = ref<Item | null>(null)
const lostItems = ref<Item[]>([])
const form = reactive({ related_lost_item_id: '', verification_detail: '' })
const loading = ref(true)
const busy = ref(false)
const error = ref('')

const compatibleLostItems = computed(() => lostItems.value.filter((item) => item.category === foundItem.value?.category))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [foundResponse, lostResponse] = await Promise.all([
      api<{ data: Item }>(`/items/${route.params.foundId}/`),
      api<{ data: { items: Item[] } }>('/items/?kind=LOST&mine=true&page_size=100'),
    ])
    foundItem.value = foundResponse.data
    lostItems.value = lostResponse.data.items
    form.related_lost_item_id = compatibleLostItems.value[0]?.id ?? ''
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '无法读取认领信息'
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!form.related_lost_item_id) return
  busy.value = true
  error.value = ''
  try {
    const response = await api<{ data: { id: string } }>('/claims/', {
      method: 'POST',
      body: JSON.stringify({
        found_item_id: route.params.foundId,
        related_lost_item_id: form.related_lost_item_id,
        statement: form.verification_detail,
        evidence: { verification_detail: form.verification_detail },
      }),
    })
    await router.push(`/claims/${response.data.id}`)
  } catch (reason) {
    error.value = reason instanceof ApiError ? reason.message : '提交失败'
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page claim-page">
    <h1 class="page-title">申请认领</h1>
    <p v-if="loading" class="state">正在读取信息…</p>
    <form v-else-if="foundItem" class="panel claim-form" @submit.prevent="submit">
      <div class="item-summary">
        <strong>{{ foundItem.title }}</strong>
        <span>{{ foundItem.category_name }} · {{ foundItem.station_name || '拾取者暂存' }}</span>
      </div>

      <template v-if="compatibleLostItems.length">
        <label>
          <span>关联我发布的遗失线索 *</span>
          <select v-model="form.related_lost_item_id" required>
            <option v-for="item in compatibleLostItems" :key="item.id" :value="item.id">{{ item.title }}</option>
          </select>
        </label>
        <label>
          <span>只有失主知道的特征 *</span>
          <textarea
            v-model="form.verification_detail"
            required
            rows="5"
            maxlength="1000"
            placeholder="例如保护壳内侧的划痕、钥匙组合或其他未公开特征"
          />
        </label>
        <p v-if="error" class="error">{{ error }}</p>
        <footer><button class="button button-brand" :disabled="busy">{{ busy ? '提交中…' : '提交认领申请' }}</button></footer>
      </template>

      <div v-else class="empty">
        <strong>请先发布同类别的遗失线索</strong>
        <RouterLink to="/publish/lost" class="button button-brand">发布遗失线索</RouterLink>
      </div>
    </form>
    <p v-else class="state error">{{ error || '未找到招领信息' }}</p>
  </div>
</template>

<style scoped>
.claim-page{max-width:820px}.claim-form{display:grid;gap:22px;margin-top:30px;padding:32px}.item-summary{display:grid;gap:6px;padding-bottom:20px;border-bottom:1px solid var(--ct-border)}.item-summary span,.claim-form label>span{color:var(--ct-text-muted);font-size:13px}.claim-form label>span{display:block;margin-bottom:8px}.claim-form select,.claim-form textarea{width:100%;padding:13px;color:var(--ct-text);border:1px solid var(--ct-border);border-radius:11px;background:var(--ct-bg-soft)}.claim-form footer{display:flex;justify-content:flex-end}.state,.empty{display:grid;place-items:center;gap:16px;min-height:240px;color:var(--ct-text-muted)}.error{color:var(--ct-danger)}
</style>
