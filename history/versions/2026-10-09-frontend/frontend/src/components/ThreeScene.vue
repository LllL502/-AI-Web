<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

type SceneMode = 'campus' | 'clue-map' | 'match'
type MatchNode = { label: string; score: number }
type ClueHotspot = { label: string; count: number }
const props = withDefaults(defineProps<{
  mode: SceneMode
  label: string
  fallbackItems?: string[]
  matchSourceLabel?: string
  matchCandidates?: MatchNode[]
  clueHotspots?: ClueHotspot[]
}>(), { fallbackItems: () => [], matchSourceLabel: '匹配源线索', matchCandidates: () => [], clueHotspots: () => [] })
const emit = defineEmits<{ select: [label: string] }>()
const host = ref<HTMLDivElement | null>(null)
const supported = ref(true)
const selected = ref('')
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
const fallbackTitle = computed(() => props.mode === 'match' ? '二维候选关系' : '二维校园热点')

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let controls: OrbitControls | null = null
let frameId = 0
let observer: ResizeObserver | null = null
let pointerStart = new THREE.Vector2()
const raycaster = new THREE.Raycaster()
const pointer = new THREE.Vector2()
const interactive: THREE.Object3D[] = []
const ownedTextures: THREE.Texture[] = []

function createLabelSprite(text: string, color = '#f5b942') {
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 64
  const context = canvas.getContext('2d')!
  context.fillStyle = 'rgba(7,17,31,.78)'
  context.roundRect(2, 2, 252, 60, 16)
  context.fill()
  context.strokeStyle = color
  context.strokeRect(3, 3, 250, 58)
  context.fillStyle = '#f4f7fb'
  context.font = '26px Microsoft YaHei, sans-serif'
  context.textAlign = 'center'
  context.textBaseline = 'middle'
  context.fillText(text, 128, 33)
  const texture = new THREE.CanvasTexture(canvas)
  ownedTextures.push(texture)
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false })
  const sprite = new THREE.Sprite(material)
  sprite.scale.set(3.2, .8, 1)
  return sprite
}

function buildCampus(target: THREE.Scene, clueMode = false) {
  const grid = new THREE.GridHelper(22, 22, 0x356586, 0x173149)
  target.add(grid)
  const defaults = ['图书馆', '教学楼', '体育馆', '食堂', '宿舍区', '校门'].map((label, index) => ({ label, count: [12, 7, 4, 9, 14, 3][index] }))
  const hotspots = clueMode && props.clueHotspots.length ? props.clueHotspots.slice(0, 6) : defaults
  const positions = [[-5, -3], [0, -4], [5, -2], [-4, 3], [1, 3], [6, 4]]
  hotspots.forEach((entry, index) => {
    const name = entry.label
    const [x, z] = positions[index]
    const height = 1.2 + (index % 3) * .55
    const building = new THREE.Mesh(
      new THREE.BoxGeometry(2.5, height, 2),
      new THREE.MeshStandardMaterial({ color: clueMode ? 0x173a57 : 0x193653, roughness: .7, metalness: .1 }),
    )
    building.position.set(x, height / 2, z)
    building.userData.label = name
    target.add(building)
    interactive.push(building)
    if (clueMode) {
      const count = entry.count
      const marker = new THREE.Mesh(
        new THREE.SphereGeometry(.28 + count / 80, 20, 20),
        new THREE.MeshStandardMaterial({ color: count > 10 ? 0xff9d55 : 0xf5b942, emissive: 0x5a3300, emissiveIntensity: .8 }),
      )
      marker.position.set(x, height + .6, z)
      marker.userData.label = `${name} · ${count} 条公开线索`
      target.add(marker)
      interactive.push(marker)
    }
  })
}

function buildMatch(target: THREE.Scene) {
  const center = new THREE.Mesh(new THREE.IcosahedronGeometry(1.05, 2), new THREE.MeshStandardMaterial({ color: 0x62b4ff, emissive: 0x143a61, emissiveIntensity: .7 }))
  center.userData.label = props.matchSourceLabel
  center.position.y = .4
  target.add(center)
  interactive.push(center)
  const candidates = props.matchCandidates
  candidates.forEach((entry, index) => {
    const angle = (index / candidates.length) * Math.PI * 2
    const distance = 4.8 - entry.score * 2.1
    const point = new THREE.Vector3(Math.cos(angle) * distance, .35, Math.sin(angle) * distance)
    const node = new THREE.Mesh(
      new THREE.SphereGeometry(.38 + entry.score * .28, 24, 24),
      new THREE.MeshStandardMaterial({ color: entry.score >= .8 ? 0xf5b942 : entry.score >= .6 ? 0x52d39a : 0x7188a3, emissive: 0x2a2105, emissiveIntensity: .5 }),
    )
    node.position.copy(point)
    node.userData.label = entry.label
    target.add(node)
    interactive.push(node)
    const geometry = new THREE.BufferGeometry().setFromPoints([center.position, point])
    target.add(new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: 0x5f7897, transparent: true, opacity: .35 + entry.score * .5 })))
  })
}

function init() {
  if (!host.value) return
  try {
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('webgl2') || canvas.getContext('webgl')
    if (!context) throw new Error('WebGL unavailable')
    renderer = new THREE.WebGLRenderer({ canvas, context: context as WebGLRenderingContext, antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    host.value.appendChild(renderer.domElement)
    scene = new THREE.Scene()
    scene.fog = new THREE.FogExp2(0x07111f, .045)
    camera = new THREE.PerspectiveCamera(45, 1, .1, 100)
    camera.position.set(10, 9, 12)
    controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = !reduceMotion.matches
    controls.maxPolarAngle = Math.PI / 2.05
    controls.minDistance = 5
    controls.maxDistance = 26
    targetLights(scene)
    if (props.mode === 'campus') buildCampus(scene)
    else if (props.mode === 'clue-map') buildCampus(scene, true)
    else buildMatch(scene)
    const label = createLabelSprite(props.mode === 'match' ? '公开证据关系 · 示意' : '校园布局 · 示意')
    label.position.set(0, props.mode === 'match' ? 4.2 : 5.5, 0)
    scene.add(label)
    renderer.domElement.addEventListener('pointerdown', onPointerDown)
    renderer.domElement.addEventListener('pointerup', onPointerUp)
    renderer.domElement.addEventListener('webglcontextlost', onContextLost)
    observer = new ResizeObserver(resize)
    observer.observe(host.value)
    document.addEventListener('visibilitychange', onVisibility)
    reduceMotion.addEventListener('change', onMotionChange)
    resize()
    animate()
  } catch {
    supported.value = false
    dispose()
  }
}

function targetLights(target: THREE.Scene) {
  target.add(new THREE.HemisphereLight(0x8bc8ff, 0x091220, 2.1))
  const key = new THREE.DirectionalLight(0xffd892, 3.2)
  key.position.set(5, 10, 7)
  target.add(key)
  const rim = new THREE.PointLight(0x2b8cff, 20, 24)
  rim.position.set(-8, 4, -6)
  target.add(rim)
}

function resize() {
  if (!host.value || !renderer || !camera) return
  const { width, height } = host.value.getBoundingClientRect()
  renderer.setSize(Math.max(width, 1), Math.max(height, 1), false)
  camera.aspect = width / Math.max(height, 1)
  camera.updateProjectionMatrix()
  if (reduceMotion.matches) renderer.render(scene!, camera)
}

function animate() {
  cancelAnimationFrame(frameId)
  if (!renderer || !scene || !camera || document.hidden) return
  controls?.update()
  renderer.render(scene, camera)
  if (!reduceMotion.matches) frameId = requestAnimationFrame(animate)
}

function onPointerDown(event: PointerEvent) { pointerStart.set(event.clientX, event.clientY) }
function onPointerUp(event: PointerEvent) {
  if (!renderer || !camera || !scene || pointerStart.distanceTo(new THREE.Vector2(event.clientX, event.clientY)) > 5) return
  const rect = renderer.domElement.getBoundingClientRect()
  pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1)
  raycaster.setFromCamera(pointer, camera)
  const hit = raycaster.intersectObjects(interactive, false)[0]
  if (hit?.object.userData.label) {
    selected.value = hit.object.userData.label
    emit('select', selected.value)
  }
}
function onContextLost(event: Event) { event.preventDefault(); supported.value = false; dispose() }
function onVisibility() { if (!document.hidden) animate(); else cancelAnimationFrame(frameId) }
function onMotionChange() { animate() }

function dispose() {
  cancelAnimationFrame(frameId)
  observer?.disconnect()
  observer = null
  document.removeEventListener('visibilitychange', onVisibility)
  reduceMotion.removeEventListener('change', onMotionChange)
  controls?.dispose()
  scene?.traverse((object) => {
    const mesh = object as THREE.Mesh
    mesh.geometry?.dispose?.()
    const materials = Array.isArray(mesh.material) ? mesh.material : mesh.material ? [mesh.material] : []
    materials.forEach((material) => material.dispose())
  })
  ownedTextures.splice(0).forEach((texture) => texture.dispose())
  renderer?.domElement.removeEventListener('pointerdown', onPointerDown)
  renderer?.domElement.removeEventListener('pointerup', onPointerUp)
  renderer?.domElement.removeEventListener('webglcontextlost', onContextLost)
  renderer?.dispose()
  renderer?.forceContextLoss()
  renderer?.domElement.remove()
  interactive.splice(0)
  renderer = null
  controls = null
  camera = null
  scene = null
}

onMounted(init)
onBeforeUnmount(dispose)
watch(() => props.mode, () => { dispose(); supported.value = true; init() })
</script>

<template>
  <div class="three-shell">
    <div v-if="supported" ref="host" class="three-host" role="img" :aria-label="label"></div>
    <div v-else class="scene-fallback" role="region" :aria-label="`${label}的二维回退`">
      <p class="eyebrow">{{ fallbackTitle }}</p>
      <button v-for="item in fallbackItems" :key="item" type="button" @click="emit('select', item)">{{ item }}</button>
      <p v-if="!fallbackItems.length" class="muted">WebGL 不可用。所有关键证据仍可在本页二维列表中查看。</p>
    </div>
    <div class="scene-toolbar">
      <span>拖拽旋转 · 滚轮缩放 · 点击节点</span>
      <strong v-if="selected">{{ selected }}</strong>
    </div>
  </div>
</template>

<style scoped>
.three-shell { position: relative; min-height: 480px; overflow: hidden; border: 1px solid var(--ct-border); border-radius: var(--ct-radius-lg); background: radial-gradient(circle at 50% 30%, #153759, #081321 70%); }
.three-host { position: absolute; inset: 0; }
.three-host :deep(canvas) { display: block; width: 100%; height: 100%; cursor: grab; }
.scene-toolbar { position: absolute; z-index: 2; right: 18px; bottom: 18px; left: 18px; display: flex; justify-content: space-between; gap: 16px; padding: 10px 13px; color: var(--ct-text-muted); border: 1px solid var(--ct-border); border-radius: 12px; background: rgba(7,17,31,.76); backdrop-filter: blur(12px); font-size: 12px; pointer-events: none; }
.scene-toolbar strong { color: var(--ct-brand-strong); }
.scene-fallback { display: grid; align-content: center; gap: 12px; min-height: 480px; padding: 36px; }
.scene-fallback button { padding: 12px; color: var(--ct-text); border: 1px solid var(--ct-border); border-radius: 12px; background: var(--ct-surface); text-align: left; }
@media (max-width: 700px) { .three-shell, .scene-fallback { min-height: 390px; } .scene-toolbar { flex-direction: column; } }
</style>
