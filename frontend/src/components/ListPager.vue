<script setup lang="ts">
import {computed} from 'vue'
const props=withDefaults(defineProps<{page:number;total:number;pageSize?:number;busy?:boolean}>(),{pageSize:20,busy:false})
const emit=defineEmits<{change:[page:number]}>()
const pages=computed(()=>Math.max(1,Math.ceil(props.total/props.pageSize)))
</script>
<template><nav v-if="pages>1" class="list-pager" aria-label="列表分页"><button type="button" :disabled="busy||page<=1" @click="emit('change',page-1)">上一页</button><span>第 {{page}} / {{pages}} 页 · 共 {{total}} 条</span><button type="button" :disabled="busy||page>=pages" @click="emit('change',page+1)">下一页</button></nav></template>
<style scoped>.list-pager{display:flex;align-items:center;justify-content:center;gap:16px;margin:24px 0;flex-wrap:wrap;font-size:14px}.list-pager button{padding:10px 16px;border:1px solid var(--ct-border);border-radius:10px;background:white;color:var(--ct-text);cursor:pointer}.list-pager button:disabled{opacity:.45;cursor:default}</style>