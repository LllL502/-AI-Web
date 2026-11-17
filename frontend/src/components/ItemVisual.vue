<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
const props = withDefaults(defineProps<{ title: string; category?: string; color?: string; imageUrl?: string; isDemo?:boolean;imageNote?:string; variant?: 'thumbnail' | 'gallery' | 'detail' }>(), { category: '', color: '', variant: 'thumbnail' })
const failed = ref(false)
watch(() => props.imageUrl, () => { failed.value = false })
const publicImage = computed(() => {
  if (!props.imageUrl || failed.value) return ''
  try {
    const url = new URL(props.imageUrl, window.location.origin)
    return ['http:', 'https:'].includes(url.protocol) ? url.href : ''
  } catch { return '' }
})
const text = computed(() => `${props.category} ${props.title}`)
const icon = computed(() => /钥匙/.test(text.value) ? 'key' : /卡|证件/.test(text.value) ? 'card' : /书|学习|文具/.test(text.value) ? 'book' : /电子|数码|耳机|电脑|设备/.test(text.value) ? 'laptop' : 'box')
</script>
<template>
  <div class="item-photo" :class="`item-photo--${variant}`">
    <img v-if="publicImage" :src="publicImage" :alt="title" loading="lazy" decoding="async" @error="failed = true" />
    <span v-if="publicImage&&(isDemo||publicImage.includes('/demo-reference/'))" class="photo-kind" title="演示参考图，非该失物现场实拍">{{variant==='thumbnail'?'参考图':imageNote?.includes('合成')?'演示示意图':'演示参考图'}}</span><div v-if="!publicImage" class="photo-placeholder"><AppIcon :name="icon" /><span>暂无实拍图</span></div>
  </div>
</template>
<style scoped>
.photo-kind{position:absolute;left:7px;bottom:7px;padding:3px 6px;border-radius:6px;background:#ffffffed;color:#354766;font-size:12px;line-height:1.4;white-space:nowrap}

.item-photo { position: relative; overflow: hidden; background: #e9e2d6; border-radius: 8px; isolation: isolate; }
.item-photo img { display: block; width: 100%; height: 100%; object-fit: cover; }
.item-photo--thumbnail { width: 116px; height: 128px; flex: 0 0 auto; }
.item-photo--gallery { height: 190px; border-radius: 0; }
.item-photo--detail { min-height: 420px; height: 100%; }
.item-photo--detail img { min-height: 420px; object-fit: contain; }
.photo-placeholder { display: grid; height: 100%; min-height: inherit; place-content: center; justify-items: center; gap: 10px; color: var(--ct-info); }
.photo-placeholder svg { font-size: 38px; }
.photo-placeholder span { font-size: 11px; color: var(--ct-text-muted); }
@media(max-width:600px) { .item-photo--thumbnail { width: 95px; height: 118px; }.item-photo--detail,.item-photo--detail img { min-height: 260px; } }
</style>
