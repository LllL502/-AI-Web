<script setup lang="ts">
defineProps<{ speaking?: boolean }>()
</script>
<template>
  <svg class="assistant-robot" :class="{ speaking }" viewBox="0 0 64 64" fill="none" aria-hidden="true">
    <defs>
      <linearGradient id="assistant-robot-shell" x1="18" y1="18" x2="47" y2="56" gradientUnits="userSpaceOnUse">
        <stop stop-color="white" /><stop offset="1" stop-color="#c5dcf9" />
      </linearGradient>
      <linearGradient id="assistant-robot-face" x1="19" y1="29" x2="45" y2="45" gradientUnits="userSpaceOnUse">
        <stop stop-color="#173b70" /><stop offset="1" stop-color="#0c254d" />
      </linearGradient>
    </defs>
    <ellipse cx="32" cy="57" rx="19" ry="3" fill="#2167cc" opacity=".12" />
    <path d="M32 20v-7" stroke="#6c9de0" stroke-width="3" stroke-linecap="round" />
    <circle cx="32" cy="10" r="4" fill="#3e85ef" />
    <rect x="5" y="31" width="7" height="15" rx="3.5" fill="#4385e8" />
    <rect x="52" y="31" width="7" height="15" rx="3.5" fill="#4385e8" />
    <rect x="10" y="20" width="44" height="34" rx="16" fill="url(#assistant-robot-shell)" stroke="#b6d0ef" stroke-width="1.5" />
    <rect x="16" y="27" width="32" height="21" rx="10.5" fill="url(#assistant-robot-face)" />
    <g class="robot-eyes"><ellipse cx="25" cy="37" rx="3" ry="4" fill="#7ce4ff" />
    <ellipse cx="39" cy="37" rx="3" ry="4" fill="#7ce4ff" /></g>
    <path class="robot-mouth" d="M29 43c2 1.3 4 1.3 6 0" stroke="#72bcf7" stroke-width="1.5" stroke-linecap="round" />
    <path d="m48 12 1.2 3.8L53 17l-3.8 1.2L48 22l-1.2-3.8L43 17l3.8-1.2L48 12Z" fill="#72b8fc" />
  </svg>
</template>

<style scoped>
.assistant-robot{display:block;width:100%;height:100%;overflow:visible}
.robot-eyes{transform-origin:32px 37px;animation:robot-blink 5.5s infinite}.speaking .robot-mouth{transform-origin:32px 43px;animation:robot-talk .3s infinite alternate}
@keyframes robot-blink{0%,43%,47%,100%{transform:scaleY(1)}45%{transform:scaleY(.12)}}
@keyframes robot-talk{to{transform:scaleY(2.3)}}
@media(prefers-reduced-motion:reduce){.robot-eyes,.speaking .robot-mouth{animation:none}}
</style>
