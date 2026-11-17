<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
const props = withDefaults(defineProps<{ title: string; category?: string; color?: string; imageUrl?: string; variant?: 'thumbnail' | 'gallery' | 'detail' }>(), { category: '', color: '', variant: 'thumbnail' })
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
const statedColor = computed(() => `${props.color} ${props.title}`)
const sample = computed(() => {
  // 本地图片只是“同类且同色”的示意图，不能为了填充卡片而展示相反颜色。
  // 颜色不匹配时回退到中性图标，避免“银色水杯配蓝色照片”这类误导。
  if (/耳机/.test(text.value) && /黑色|深色/.test(statedColor.value)) return '/local-assets/sample-earbuds.webp'
  if (/水杯|水瓶|保温杯|杯子/.test(text.value) && /蓝色|藏蓝|深蓝/.test(statedColor.value)) return '/local-assets/sample-bottle.webp'
  if (/校园卡|一卡通|学生卡|证件卡片/.test(text.value) && /绿色|青绿/.test(statedColor.value)) return '/local-assets/sample-card.webp'
  return ''
})
const sampleFailed = ref(false)
watch(sample, () => { sampleFailed.value = false })
const icon = computed(() => /钥匙/.test(text.value) ? 'key' : /卡|证件/.test(text.value) ? 'card' : /书|学习|文具/.test(text.value) ? 'book' : /电子|数码|耳机|电脑|设备/.test(text.value) ? 'laptop' : 'box')
</script>
<template>
  <div class="item-photo" :class="`item-photo--${variant}`">
    <img v-if="publicImage" :src="publicImage" :alt="title" loading="lazy" decoding="async" @error="failed = true" />
    <template v-else-if="sample && !sampleFailed"><img :src="sample" :alt="`${color || ''}${category || title}同色类别示意图，并非该物品的实拍照片`" loading="lazy" decoding="async" @error="sampleFailed = true" /><span class="sample-label">同色类别示意图</span></template>
    <div v-else class="photo-placeholder"><AppIcon :name="icon" /><span>暂无实拍图</span></div>
  </div>
</template>
<style scoped>
.item-photo { position: relative; overflow: hidden; background: #e9e2d6; border-radius: 8px; isolation: isolate; }
.item-photo img { display: block; width: 100%; height: 100%; object-fit: cover; }
.item-photo--thumbnail { width: 116px; height: 128px; flex: 0 0 auto; }
.item-photo--gallery { height: 190px; border-radius: 0; }
.item-photo--detail { min-height: 420px; height: 100%; }
.item-photo--detail img { min-height: 420px; object-fit: contain; }
.sample-label { position: absolute; right: 5px; bottom: 5px; left: 5px; width: fit-content; margin: auto; padding: 3px 6px; border-radius: 3px; background: rgba(255,253,248,.94); color: #635b4e; font-size: 9px; line-height: 1.4; }
.photo-placeholder { display: grid; height: 100%; min-height: inherit; place-content: center; justify-items: center; gap: 10px; color: var(--ct-info); }
.photo-placeholder svg { font-size: 38px; }
.photo-placeholder span { font-size: 11px; color: var(--ct-text-muted); }
@media(max-width:600px) { .item-photo--thumbnail { width: 95px; height: 118px; }.item-photo--detail,.item-photo--detail img { min-height: 260px; } }
</style>
