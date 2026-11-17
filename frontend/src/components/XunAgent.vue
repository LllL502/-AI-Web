<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import XunAgentFallback from './XunAgentFallback.vue'
import type { XunGesture } from '../utils/xunAgentScene'
const props=withDefaults(defineProps<{busy?:boolean;speaking?:boolean;gesture?:XunGesture}>(),{gesture:'idle'})
const host=ref<HTMLDivElement>(),ready=ref(false)
let disposed=false,frame=0,visible=true,started=performance.now(),resize:ResizeObserver|undefined,intersection:IntersectionObserver|undefined
let teardown:(()=>void)|undefined, redraw:(()=>void)|undefined
const reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)')
watch(()=>props.gesture,()=>{started=performance.now();redraw?.()})
watch(()=>[props.speaking,props.busy],()=>redraw?.())
onMounted(async()=>{
  if(!window.WebGLRenderingContext || !host.value)return
  try{
    const [THREE,{createXunRig,poseXun,disposeXunScene}]=await Promise.all([import('three'),import('../utils/xunAgentScene')])
    if(disposed||!host.value)return
    const renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,powerPreference:'low-power'})
    renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));renderer.setClearColor(0,0)
    renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05
    const scene=new THREE.Scene(),camera=new THREE.OrthographicCamera(-1.8,1.8,2.0,-2.0,.1,20)
    camera.position.set(0,1.70,7);camera.lookAt(0,1.70,0)
    scene.add(new THREE.HemisphereLight(0xffffff,0x8ca9cf,2.6))
    const key=new THREE.DirectionalLight(0xffffff,2);key.position.set(-3,5,5);scene.add(key)
    const rim=new THREE.DirectionalLight(0x9ce5ff,1.8);rim.position.set(3,2,-4);scene.add(rim)
    const logo=await new THREE.TextureLoader().loadAsync('/xunji-mark.svg')
    if(disposed){logo.dispose();renderer.dispose();return}
    const rig=createXunRig(logo);scene.add(rig.root)
    const shadow=new THREE.Mesh(new THREE.CircleGeometry(.65,40),new THREE.MeshBasicMaterial({color:0x4383c2,transparent:true,opacity:.10,depthWrite:false}))
    shadow.rotation.x=-Math.PI/2;shadow.position.y=.01;shadow.scale.y=.55;scene.add(shadow)
    renderer.domElement.setAttribute('aria-hidden','true');host.value.appendChild(renderer.domElement)
    const size=()=>{
      if(!host.value)return
      const w=host.value.clientWidth||142,h=host.value.clientHeight||152,aspect=w/h
      camera.left=-2.0*aspect;camera.right=2.0*aspect;camera.updateProjectionMatrix();renderer.setSize(w,h,false)
      redraw?.()
    }
    redraw=()=>{
      if(disposed||!visible)return
      const now=performance.now()
      poseXun(rig,props.gesture,(now-started)/1000,now/1000,props.speaking,reduced?.matches)
      renderer.render(scene,camera)
    }
    let lastFrame=0
    const tick=(now:number)=>{if(disposed)return;frame=requestAnimationFrame(tick);if(visible&&!document.hidden&&!reduced?.matches&&now-lastFrame>32){lastFrame=now;redraw?.()}}
    const mediaChanged=()=>redraw?.()
    reduced?.addEventListener('change',mediaChanged)
    const lost=(event:Event)=>{event.preventDefault();ready.value=false;cancelAnimationFrame(frame)}
    renderer.domElement.addEventListener('webglcontextlost',lost)
    resize=new ResizeObserver(size);resize.observe(host.value)
    if('IntersectionObserver'in window){intersection=new IntersectionObserver(entries=>{visible=entries[0]?.isIntersecting??false;if(visible)redraw?.()});intersection.observe(host.value)}
    teardown=()=>{reduced?.removeEventListener('change',mediaChanged);renderer.domElement.removeEventListener('webglcontextlost',lost);disposeXunScene(scene);renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove()}
    size();redraw();ready.value=true;frame=requestAnimationFrame(tick)
  }catch{ready.value=false;teardown?.()}
})
onBeforeUnmount(()=>{disposed=true;cancelAnimationFrame(frame);resize?.disconnect();intersection?.disconnect();teardown?.()})
</script>
<template><div class="xun-agent" :class="[gesture,{busy,speaking}]" :data-renderer="ready?'webgl':'fallback'"><div ref="host" class="xun-three-host" :class="{'is-ready':ready}"/><XunAgentFallback v-if="!ready" :busy="busy" :speaking="speaking" :gesture="gesture"/></div></template>
<style scoped>
.xun-agent{position:relative;display:block;width:100%;height:100%}.xun-three-host{position:absolute;inset:0;opacity:0;pointer-events:none}.xun-three-host.is-ready{opacity:1}.xun-three-host :deep(canvas){display:block;width:100%;height:100%}
</style>
