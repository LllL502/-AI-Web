<script setup lang="ts">
import { useId } from 'vue'
withDefaults(defineProps<{ busy?: boolean; speaking?: boolean; gesture?: 'idle'|'wave'|'spin'|'wink' }>(), {gesture:'idle'})
const id = useId().replaceAll(':', '')
</script>
<template>
  <svg class="xun-agent" :class="[gesture,{ busy, speaking }]" viewBox="0 0 160 180" fill="none" aria-hidden="true">
    <defs>
      <linearGradient :id="id" x1="45" y1="30" x2="111" y2="158" gradientUnits="userSpaceOnUse"><stop stop-color="#fff"/><stop offset=".65" stop-color="#eef7ff"/><stop offset="1" stop-color="#c9e3ff"/></linearGradient>
      <linearGradient :id="`${id}-face`" x1="46" y1="56" x2="111" y2="94" gradientUnits="userSpaceOnUse"><stop stop-color="#1b4366"/><stop offset="1" stop-color="#102c4b"/></linearGradient>
    </defs>
    <ellipse cx="80" cy="171" rx="32" ry="5" fill="#2569bb" opacity=".1"/>
    <g class="agent-body">
      <g class="agent-foot left"><path d="M59 143c-11 2-17 10-13 17 3 7 19 7 25 1l5-16" :fill="`url(#${id})`" stroke="#a9cdef" stroke-width="1.5"/></g>
      <g class="agent-foot right"><path d="M101 143c11 2 17 10 13 17-3 7-19 7-25 1l-5-16" :fill="`url(#${id})`" stroke="#a9cdef" stroke-width="1.5"/></g>
      <path d="M58 104c-8 10-13 28-10 40 4 16 57 18 64 0 4-11-1-31-10-40" :fill="`url(#${id})`" stroke="#a9cdef" stroke-width="1.8"/>
      <ellipse cx="80" cy="134" rx="19" ry="17" fill="#e2f1ff"/>
      <image :href="'/xunji-mark.svg'" x="69" y="122" width="22" height="22"/>
      <g class="agent-arm-left"><path d="M51 112c-9-2-16 5-15 14 1 8 9 11 13 5l9-10" :fill="`url(#${id})`" stroke="#a9cdef" stroke-width="1.6"/><path d="m39 127 4 1" stroke="#87baf0" stroke-width="2" stroke-linecap="round"/></g>
      <g class="agent-arm-right"><path d="M108 115c7 7 16 3 20-4 4-8 1-16-6-17-7-2-7 8-15 9" :fill="`url(#${id})`" stroke="#a9cdef" stroke-width="1.6"/><path d="m121 99 3 2m-5 2 4 2" stroke="#87baf0" stroke-width="1.7" stroke-linecap="round"/></g>
      <g class="agent-head">
        <rect x="52" y="0" width="15" height="38" rx="7.5" fill="#f1f8ff" stroke="#a9cdef"/><rect x="57" y="5" width="5" height="24" rx="2.5" fill="#8df2ed"/>
        <path d="M98 33V13q0-12 10-9l11 9q5 7-3 11l-8-5v14" fill="#f1f8ff" stroke="#a9cdef" stroke-width="2"/>
        <path d="M104 24V12l10 7" stroke="#8df2ed" stroke-width="5" stroke-linecap="round"/>
        <ellipse cx="30" cy="70" rx="8" ry="14" fill="#71aaf1"/><ellipse cx="130" cy="70" rx="8" ry="14" fill="#71aaf1"/>
        <path d="M80 28c-34 0-51 15-51 42 0 28 16 43 51 43s51-15 51-43c0-27-17-42-51-42Z" :fill="`url(#${id})`" stroke="#a9cdef" stroke-width="1.8"/>
        <path d="M80 45c-25 0-39 9-39 27 0 20 13 28 39 28s39-8 39-28c0-18-14-27-39-27Z" :fill="`url(#${id}-face)`"/>
        <g class="agent-eyes"><ellipse class="eye-left" cx="64" cy="70" rx="6" ry="8" fill="#8df2f2"/><ellipse class="eye-right" cx="96" cy="70" rx="6" ry="8" fill="#8df2f2"/></g>
        <ellipse cx="52" cy="83" rx="5" ry="2.7" fill="#fa9fba" opacity=".65"/><ellipse cx="108" cy="83" rx="5" ry="2.7" fill="#fa9fba" opacity=".65"/>
        <path class="agent-mouth" d="M74 84q6 7 12 0" stroke="#9af1ef" stroke-width="2.5" stroke-linecap="round"/>
        <path d="M43 44q10-9 23-9" stroke="white" stroke-width="4" stroke-linecap="round"/>
      </g>
    </g>
  </svg>
</template>
<style scoped>
.xun-agent{display:block;width:100%;height:100%;overflow:visible;filter:drop-shadow(0 5px 5px #2b67a015)}.agent-body{transform-origin:80px 154px;animation:agent-breathe 5s ease-in-out infinite}.agent-arm-right{transform-origin:109px 113px;animation:none}.agent-head{transform-origin:80px 103px;animation:none}.agent-eyes{transform-origin:80px 70px;animation:agent-blink 5.4s infinite}.eye-right{transform-origin:96px 70px;animation:none}.agent-foot.left{transform-origin:64px 146px;animation:none}.speaking .agent-mouth{transform-origin:80px 84px;animation:agent-talk .28s infinite alternate}.busy .agent-light{animation:agent-pulse .8s infinite alternate}
.wave .agent-arm-right{animation:agent-greeting 2.5s ease-in-out 1}.wink .eye-right{animation:agent-single-wink 2.2s ease-in-out 1}.spin .agent-body{animation:agent-hop 2.2s ease-in-out 1}
@keyframes agent-breathe{50%{transform:translateY(-2px)}}@keyframes agent-greeting{0%,100%{transform:rotate(0)}20%,60%{transform:rotate(-28deg)}40%,80%{transform:rotate(5deg)}}@keyframes agent-single-wink{0%,25%,75%,100%{transform:scaleY(1)}35%,65%{transform:scaleY(.08)}}@keyframes agent-hop{0%,100%{transform:translateY(0) rotate(0)}30%{transform:translateY(-5px) rotate(-8deg)}65%{transform:translateY(-3px) rotate(8deg)}}
@keyframes agent-blink{0%,43%,47%,100%{transform:scaleY(1)}45%{transform:scaleY(.1)}}@keyframes agent-talk{to{transform:scaleY(1.5)}}@keyframes agent-pulse{to{opacity:.3}}
@media(prefers-reduced-motion:reduce){.agent-body,.agent-arm-right,.agent-head,.agent-eyes,.eye-right,.agent-foot.left,.speaking .agent-mouth,.busy .agent-light,.wave .agent-arm-right,.wink .eye-right,.spin .agent-body{animation:none}}
</style>
