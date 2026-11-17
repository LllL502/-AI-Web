<script setup lang="ts">
defineProps<{ name: 'search' | 'map' | 'spark' | 'user' | 'plus' | 'shield' | 'bell' | 'arrow' | 'box' }>()
</script>

<template>
  <svg class="app-icon" viewBox="0 0 24 24" aria-hidden="true">
    <path v-if="name === 'search'" d="m21 21-4.3-4.3m2.3-5.2a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z" />
    <path v-else-if="name === 'map'" d="m3 6 5-3 8 3 5-3v15l-5 3-8-3-5 3V6Zm5-3v15m8-12v15" />
    <path v-else-if="name === 'spark'" d="m12 2 1.6 5.4L19 9l-5.4 1.6L12 16l-1.6-5.4L5 9l5.4-1.6L12 2Zm7 13 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" />
    <path v-else-if="name === 'user'" d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm7 9a7 7 0 0 0-14 0" />
    <path v-else-if="name === 'plus'" d="M12 5v14M5 12h14" />
    <path v-else-if="name === 'shield'" d="M12 2 4 5v6c0 5 3.4 8.8 8 11 4.6-2.2 8-6 8-11V5l-8-3Zm-3 10 2 2 4-5" />
    <path v-else-if="name === 'bell'" d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Zm-8 12h4" />
    <path v-else-if="name === 'arrow'" d="m9 5 7 7-7 7" />
    <path v-else d="m4 7 8-4 8 4-8 4-8-4Zm0 0v10l8 4 8-4V7m-8 4v10" />
  </svg>
</template>

<style scoped>
.app-icon { width: 1.15em; height: 1.15em; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
</style>
