<script setup lang="ts">
import {statusLabel} from '../../utils/statusLabels'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, ApiError, readableApiError } from '../../api/client'
import AppIcon from '../../components/AppIcon.vue'
import { useAuthStore } from '../../stores/auth'
import AMapCampus from '../../components/AMapCampus.vue'

type DictionaryEntry = { id: number; name: string; parent_id: number | null }
type StationEntry = { id: number; name: string; status: string }
type CampusEntry = { id: number; name: string; school: string; is_demo: boolean }
type CoordinateCandidate = { latitude: number; longitude: number; label: string; coordinate_system: 'GCJ02' }
type MediaAsset = { id: number; file: string; thumbnail?: string; width?: number; height?: number; sort_order: number }
type PhotoEntry =
  | { key: string; kind: 'existing'; id: number; url: string }
  | { key: string; kind: 'pending'; file: File; url: string }
type PublishForm = {
  title: string
  category: string
  description: string
  brand: string
  color: string
  occurred_at: string
  location: string
  location_detail: string
  location_candidate_ids: number[]
  location_candidate_points: CoordinateCandidate[]
  station: string
}

type EditableItem = PublishForm & {
  id: string
  kind: 'LOST' | 'FOUND'
  category: number
  location: number
  station: number | null
  latitude?: string | number | null
  longitude?: string | number | null
  review_status: string
  allowed_actions: string[]
  location_candidates?: Array<{ id: number; location: number; name: string; rank: number }>
  coordinate_candidates?: Array<CoordinateCandidate & { id: number; rank: number }>
  media?: MediaAsset[]
}

const props = defineProps<{ kind?: 'LOST' | 'FOUND'; editId?: string }>()
const router = useRouter()
const auth=useAuthStore()
const activeKind = ref<'LOST' | 'FOUND'>(props.kind ?? 'LOST')
const isEditMode = computed(() => Boolean(props.editId))
const step = ref(1)
const saving = ref(false)
const metadataLoading = ref(true)
const creatingRegion = ref(false)
const processingPhotos = ref(false)
const error = ref('')
const success = ref('')
const warning = ref('')
const categories = ref<DictionaryEntry[]>([])
const locations = ref<DictionaryEntry[]>([])
const protectedLocations = ref<DictionaryEntry[]>([])
const stations = ref<StationEntry[]>([])
const campus = ref<CampusEntry | null>(null)
const form = reactive<PublishForm>({ title: '', category: '', description: '', brand: '', color: '', occurred_at: '', location: '', location_detail: '', location_candidate_ids: [], location_candidate_points: [], station: '' })
const point = ref<{ latitude: number; longitude: number } | null>(null)
const photos = ref<PhotoEntry[]>([])
const removedMediaIds = ref<number[]>([])
const savedItemId = ref(props.editId ?? '')
const editingPublished = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const draftKey = computed(() => `campustrace-draft-user-${auth.user?.id??'guest'}-${localStorage.getItem('campustrace-campus')??'demo'}-${activeKind.value.toLowerCase()}`)

const selectedCategory = computed(() => categories.value.find((entry) => String(entry.id) === form.category))
const selectedLocation = computed(() => locations.value.find((entry) => String(entry.id) === form.location))
const selectedStation = computed(() => stations.value.find((entry) => String(entry.id) === form.station))
const selectedProtectedLocations = computed(() => form.location_candidate_ids
  .map((id) => protectedLocations.value.find((entry) => entry.id === id))
  .filter((entry): entry is DictionaryEntry => Boolean(entry)))
const selectedCandidateCount = computed(() => selectedProtectedLocations.value.length + form.location_candidate_points.length)
const protectedLocationSummary = computed(() => [
  ...selectedProtectedLocations.value.map((entry) => entry.name),
  ...form.location_candidate_points.map((entry) => entry.label || `${entry.longitude.toFixed(6)}, ${entry.latitude.toFixed(6)}`),
])
const photoSlotsLeft = computed(() => Math.max(0, 3 - photos.value.length))
const currentCampusName = computed(() => {
  if (campus.value?.name) return campus.value.name
  const cachedLabel = localStorage.getItem('campustrace-campus-label') ?? ''
  return cachedLabel.split('·').at(-1)?.trim() ?? ''
})

function restoreDraft() {
  // Legacy keys have no owner: preserve them locally, but never import them into an account.
  const stored = localStorage.getItem(draftKey.value)
  if (!stored) return
  try {
    const draft = JSON.parse(stored) as Partial<Record<keyof PublishForm, unknown>>
    for (const key of Object.keys(form) as (keyof PublishForm)[]) {
      const value = draft[key]
      if (key === 'location_candidate_ids') {
        form.location_candidate_ids = Array.isArray(value)
          ? value.filter((entry): entry is number => Number.isInteger(entry)).slice(0, 5)
          : []
      } else if (key === 'location_candidate_points') {
        form.location_candidate_points = Array.isArray(value)
          ? value.filter((entry): entry is CoordinateCandidate => (
            typeof entry === 'object' && entry !== null
            && Number.isFinite(Number((entry as CoordinateCandidate).latitude))
            && Number.isFinite(Number((entry as CoordinateCandidate).longitude))
          )).slice(0, 5).map((entry) => ({
            latitude: Number(entry.latitude),
            longitude: Number(entry.longitude),
            label: String(entry.label || '地图选点'),
            coordinate_system: 'GCJ02',
          }))
          : []
      } else if (typeof value === 'string' || typeof value === 'number') {
        form[key] = String(value) as never
      }
    }
  } catch {
    localStorage.removeItem(draftKey.value)
    warning.value = '未能读取之前的本地草稿，已为你重置表单。'
  }
}

function toLocalDateTimeValue(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.slice(0, 16)
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function populateForEditing(item: EditableItem) {
  activeKind.value = item.kind
  editingPublished.value = item.review_status === 'APPROVED'
  Object.assign(form, {
    title: item.title ?? '',
    category: String(item.category ?? ''),
    description: item.description ?? '',
    brand: item.brand ?? '',
    color: item.color ?? '',
    occurred_at: toLocalDateTimeValue(item.occurred_at),
    location: String(item.location ?? ''),
    location_detail: item.location_detail ?? '',
    location_candidate_ids: (item.location_candidates ?? [])
      .sort((left, right) => left.rank - right.rank)
      .map((entry) => entry.location),
    location_candidate_points: (item.coordinate_candidates ?? [])
      .sort((left, right) => left.rank - right.rank)
      .map((entry) => ({
        latitude: Number(entry.latitude),
        longitude: Number(entry.longitude),
        label: entry.label || '地图选点',
        coordinate_system: 'GCJ02' as const,
      })),
    station: item.station ? String(item.station) : '',
  })
  if (form.location_candidate_points.length) {
    point.value = { ...form.location_candidate_points[0] }
  } else if (item.latitude != null && item.longitude != null) {
    point.value = { latitude: Number(item.latitude), longitude: Number(item.longitude) }
    form.location_candidate_points = [{ ...point.value, label: '地图选点', coordinate_system: 'GCJ02' }]
  }
  photos.value = (item.media ?? []).map((asset) => ({
    key: `existing-${asset.id}`,
    kind: 'existing' as const,
    id: asset.id,
    url: asset.thumbnail || asset.file,
  }))
}

function photoError(message: string) {
  error.value = message
  step.value = 1
}

async function compressPhoto(file: File): Promise<File> {
  if (typeof createImageBitmap !== 'function') return file
  const bitmap = await createImageBitmap(file)
  try {
    const scale = Math.min(1, 2000 / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * scale))
    canvas.height = Math.max(1, Math.round(bitmap.height * scale))
    const context = canvas.getContext('2d')
    if (!context) return file
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/webp', .82))
    if (!blob || blob.size >= file.size) return file
    const baseName = file.name.replace(/\.[^.]+$/, '') || 'photo'
    return new File([blob], `${baseName}.webp`, { type: 'image/webp', lastModified: file.lastModified })
  } finally {
    bitmap.close()
  }
}

async function selectPhotos(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = Array.from(input.files ?? [])
  input.value = ''
  error.value = ''
  if (!selected.length) return
  if (selected.length > photoSlotsLeft.value) {
    photoError(`每条线索最多上传 3 张照片，当前还可选择 ${photoSlotsLeft.value} 张。`)
    return
  }
  const allowedTypes = new Set(['image/jpeg', 'image/png', 'image/webp'])
  for (const file of selected) {
    if (!allowedTypes.has(file.type)) {
      photoError('仅支持 JPG、PNG 或 WebP 照片。')
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      photoError(`照片“${file.name}”超过 5MB，请压缩后重试。`)
      return
    }
  }

  processingPhotos.value = true
  try {
    for (const original of selected) {
      const file = await compressPhoto(original)
      photos.value.push({
        key: `pending-${crypto.randomUUID?.() ?? `${Date.now()}-${Math.random()}`}`,
        kind: 'pending',
        file,
        url: URL.createObjectURL(file),
      })
    }
  } catch {
    photoError('照片预处理失败，请换一张图片后重试。')
  } finally {
    processingPhotos.value = false
  }
}

function removePhoto(index: number) {
  const [photo] = photos.value.splice(index, 1)
  if (!photo) return
  if (photo.kind === 'existing') removedMediaIds.value.push(photo.id)
  else URL.revokeObjectURL(photo.url)
}

function movePhoto(index: number, direction: -1 | 1) {
  const target = index + direction
  if (target < 0 || target >= photos.value.length) return
  const next = [...photos.value]
  ;[next[index], next[target]] = [next[target], next[index]]
  photos.value = next
}

function replacePhotosWithSaved(media: MediaAsset[]) {
  for (const photo of photos.value) {
    if (photo.kind === 'pending') URL.revokeObjectURL(photo.url)
  }
  photos.value = media.map((asset) => ({
    key: `existing-${asset.id}`,
    kind: 'existing',
    id: asset.id,
    url: asset.thumbnail || asset.file,
  }))
  removedMediaIds.value = []
}

async function syncPhotos(itemId: string) {
  for (const mediaId of [...new Set(removedMediaIds.value)]) {
    await api(`/items/${itemId}/media/${mediaId}/`, { method: 'DELETE' })
    removedMediaIds.value = removedMediaIds.value.filter((id) => id !== mediaId)
  }

  const pending = photos.value.filter((photo): photo is Extract<PhotoEntry, { kind: 'pending' }> => photo.kind === 'pending')
  const createdByKey = new Map<string, MediaAsset>()
  if (pending.length) {
    const body = new FormData()
    for (const photo of pending) body.append('files', photo.file, photo.file.name)
    const response = await api<{ data: { created: MediaAsset[]; media: MediaAsset[] } }>(`/items/${itemId}/media/`, { method: 'POST', body })
    pending.forEach((photo, index) => createdByKey.set(photo.key, response.data.created[index]))
    // 上传一旦成功就把本地待上传项升级为服务器照片。即使后续排序接口
    // 临时失败，用户重试时也不会再次上传同一文件或创建重复媒体。
    photos.value = photos.value.map((photo) => {
      if (photo.kind === 'existing') return photo
      const asset = createdByKey.get(photo.key)
      if (!asset) throw new ApiError('服务器返回的照片数量不完整，请刷新后检查草稿。', 'invalid_media_response', 502)
      URL.revokeObjectURL(photo.url)
      return { key: `existing-${asset.id}`, kind: 'existing' as const, id: asset.id, url: asset.thumbnail || asset.file }
    })
  }

  const mediaIds = photos.value.map((photo) => photo.kind === 'existing' ? photo.id : createdByKey.get(photo.key)?.id).filter((id): id is number => typeof id === 'number')
  if (mediaIds.length) {
    const response = await api<{ data: { media: MediaAsset[] } }>(`/items/${itemId}/media-order/`, {
      method: 'PATCH',
      body: JSON.stringify({ media_ids: mediaIds }),
    })
    replacePhotosWithSaved(response.data.media)
  } else {
    replacePhotosWithSaved([])
  }
}

onBeforeUnmount(() => {
  for (const photo of photos.value) {
    if (photo.kind === 'pending') URL.revokeObjectURL(photo.url)
  }
})

/** 切换校区或字典更新后，旧草稿的数字 ID 可能已经无效。 */
function reconcileDraftWithMetadata() {
  const resetFields: string[] = []
  if (form.category && !selectedCategory.value) {
    form.category = ''
    resetFields.push('类别')
  }
  if (form.location && !selectedLocation.value) {
    form.location = ''
    point.value = null
    form.location_candidate_points = []
    resetFields.push('公开地点')
  }
  if (form.station && !selectedStation.value) {
    form.station = ''
    resetFields.push('服务站')
  }
  const validProtectedIds = new Set(protectedLocations.value.map((entry) => entry.id))
  const validCandidates = form.location_candidate_ids.filter((id) => validProtectedIds.has(id))
  if (validCandidates.length !== form.location_candidate_ids.length) {
    form.location_candidate_ids = validCandidates
    resetFields.push('受保护地点')
  }
  if (resetFields.length) {
    warning.value = `校区数据已更新，旧草稿中的${resetFields.join('、')}已失效，请重新选择。`
  }
}

async function ensureCampusRegion(): Promise<boolean> {
  creatingRegion.value = true
  error.value = ''
  try {
    const result = await api<{ data: { id: number; name: string } }>('/maps/campus-region/', { method: 'POST' })
    if (!locations.value.some((entry) => entry.id === result.data.id)) {
      locations.value.push({ ...result.data, parent_id: null })
    }
    form.location = String(result.data.id)
    return true
  } catch (reason) {
    error.value = readableApiError(reason, '无法建立公开校园区域，请稍后重试。')
    return false
  } finally {
    creatingRegion.value = false
  }
}

async function pickPoint(value: { latitude: number; longitude: number; label?: string }) {
  const candidate: CoordinateCandidate = {
    latitude: Number(value.latitude.toFixed(6)),
    longitude: Number(value.longitude.toFixed(6)),
    label: value.label?.trim() || `地图选点 ${form.location_candidate_points.length + 1}`,
    coordinate_system: 'GCJ02',
  }
  if (!form.location) {
    await ensureCampusRegion()
  }
  const duplicate = form.location_candidate_points.some((entry) => (
    entry.latitude === candidate.latitude && entry.longitude === candidate.longitude
  ))
  if (duplicate) {
    error.value = '这个地点已经在候选列表中。'
    return
  }
  if (activeKind.value === 'FOUND') {
    form.location_candidate_points = [candidate]
    form.location_candidate_ids = []
  } else if (selectedCandidateCount.value < 5) {
    form.location_candidate_points = [...form.location_candidate_points, candidate]
  } else {
    error.value = '最多可选 5 个可能遗失地点，请先移除一个。'
    return
  }
  point.value = { latitude: form.location_candidate_points[0].latitude, longitude: form.location_candidate_points[0].longitude }
  error.value = ''
}

function selectProtectedLocation(location: { id: number; name?: string }) {
  if (!protectedLocations.value.some((entry) => entry.id === location.id)) {
    error.value = '该地点不在当前校区的受保护地点字典中。'
    return
  }
  if (activeKind.value === 'FOUND') {
    // 拾获地点是已发生事实，始终保留一个结构化地点。
    form.location_candidate_ids = [location.id]
    form.location_candidate_points = []
  } else if (form.location_candidate_ids.includes(location.id)) {
    // 遗失地点是不确定假设；再次点击可取消候选。
    form.location_candidate_ids = form.location_candidate_ids.filter((id) => id !== location.id)
  } else if (selectedCandidateCount.value < 5) {
    form.location_candidate_ids = [...form.location_candidate_ids, location.id]
  } else {
    error.value = '最多可选 5 个可能遗失地点，请先移除一个。'
    return
  }
  point.value = null
  error.value = ''
}

function moveProtectedLocation(index: number, direction: -1 | 1) {
  const target = index + direction
  if (target < 0 || target >= form.location_candidate_ids.length) return
  const next = [...form.location_candidate_ids]
  ;[next[index], next[target]] = [next[target], next[index]]
  form.location_candidate_ids = next
}

function removeProtectedLocation(id: number) {
  form.location_candidate_ids = form.location_candidate_ids.filter((entry) => entry !== id)
}

function moveCoordinateLocation(index: number, direction: -1 | 1) {
  const target = index + direction
  if (target < 0 || target >= form.location_candidate_points.length) return
  const next = [...form.location_candidate_points]
  ;[next[index], next[target]] = [next[target], next[index]]
  form.location_candidate_points = next
  point.value = next[0] ? { latitude: next[0].latitude, longitude: next[0].longitude } : null
}

function removeCoordinateLocation(index: number) {
  form.location_candidate_points = form.location_candidate_points.filter((_, entryIndex) => entryIndex !== index)
  const first = form.location_candidate_points[0]
  point.value = first ? { latitude: first.latitude, longitude: first.longitude } : null
}

onMounted(async () => {
  if (!isEditMode.value) restoreDraft()
  try {
    const [metadataResponse, itemResponse] = await Promise.all([
      api<{ data: { campus: CampusEntry; categories: typeof categories.value; locations: typeof locations.value; stations: typeof stations.value } }>('/items/metadata/'),
      props.editId ? api<{ data: EditableItem }>(`/items/${props.editId}/`) : Promise.resolve(null),
    ])
    campus.value = metadataResponse.data.campus ?? null
    categories.value = metadataResponse.data.categories.filter((entry) => entry.parent_id !== null)
    protectedLocations.value = metadataResponse.data.locations.filter((entry) => entry.parent_id !== null)
    // 对外只公开到校区层级。图书馆、宿舍、操场等子区域只能进入受保护地点。
    locations.value = metadataResponse.data.locations
      .filter((entry) => entry.parent_id === null)
      .map((entry) => ({ ...entry, name: currentCampusName.value || entry.name }))
    stations.value = metadataResponse.data.stations
    if (itemResponse) {
      if (!itemResponse.data.allowed_actions.includes('edit')) {
        throw new ApiError('当前状态的信息不可编辑，请返回“我的发布”查看可用操作。', 'item_not_editable', 409)
      }
      populateForEditing(itemResponse.data)
    }
    reconcileDraftWithMetadata()
    if (!locations.value.length) await ensureCampusRegion()
    if (!form.location && locations.value[0]) form.location = String(locations.value[0].id)
  } catch (reason) {
    error.value = readableApiError(reason, '无法读取分类和地点字典。')
  } finally {
    metadataLoading.value = false
  }
})
watch(form, () => {
  if (!isEditMode.value) localStorage.setItem(draftKey.value, JSON.stringify(form))
}, { deep: true })

function validateStep(targetStep: number): boolean {
  error.value = ''
  if (targetStep >= 1 && (!form.title.trim() || !form.category || !form.description.trim())) {
    error.value = '请先完整填写标题、类别和公开描述。'
    step.value = 1
    return false
  }
  if (targetStep >= 2 && (!form.occurred_at || !form.location)) {
    error.value = '请先选择事件时间和当前校区内的公开地点。'
    step.value = 2
    return false
  }
  if (targetStep >= 2 && !selectedLocation.value) {
    form.location = ''
    error.value = '草稿中的公开地点已失效，请为当前校区重新选择。'
    step.value = 2
    return false
  }
  return true
}

function nextStep() {
  if (validateStep(step.value)) step.value += 1
}

function goToStep(target: number) {
  if (target <= step.value || validateStep(target - 1)) step.value = target
}

function saveLocalDraft() {
  localStorage.setItem(draftKey.value, JSON.stringify(form))
  error.value = ''
  success.value = photos.value.some((photo) => photo.kind === 'pending')
    ? '文字草稿已保存在当前浏览器；出于浏览器安全限制，待上传照片不会随本地草稿保留。'
    : '草稿已保存在当前浏览器，稍后可继续填写。'
}

async function save(submitAfterSave = true) {
  if (!validateStep(2)) return
  saving.value = true; error.value = ''; success.value = ''
  try {
    // 顶层坐标继续写入第一候选点以兼容旧记录；完整顺序由
    // location_candidate_points 保存，后端匹配也优先使用候选点表。
    const coordinates = point.value ? { ...point.value, coordinate_system: 'GCJ02' } : {}
    const payload = { ...form, ...coordinates, station: form.station || null, kind: activeKind.value }
    // 编辑沿用原记录并保留版本链；新建才产生新的草稿编号。
    const response = savedItemId.value
      ? await api<{ data?: { id: string }; id?: string }>(`/items/${savedItemId.value}/`, { method: 'PATCH', body: JSON.stringify(payload) })
      : await api<{ data?: { id: string }; id?: string }>('/items/', { method: 'POST', body: JSON.stringify(payload) })
    const itemId = savedItemId.value || response.data?.id || response.id
    if (!itemId) throw new ApiError('服务器未返回新线索编号，请刷新页面后重试。', 'invalid_create_response', 502)
    savedItemId.value = itemId
    await syncPhotos(itemId)
    if (submitAfterSave && !editingPublished.value) {
      const submitted = await api<{ data: { review_status: string } }>(`/items/${itemId}/submit/`, { method: 'POST' })
      if (!isEditMode.value) localStorage.removeItem(draftKey.value)
      success.value = submitted.data.review_status === 'APPROVED'
        ? '后端自动审核已通过，线索已进入广场和智能匹配。'
        : '已提交审核。自动检查发现需要人工复核的内容，复核通过前线索暂不公开。'
      setTimeout(() => router.push('/me/items'), 900)
    } else if (editingPublished.value) {
      success.value = '修改已保存，遗失广场或招领广场已同步更新。'
      if (submitAfterSave) setTimeout(() => router.push('/me/items'), 900)
    } else {
      success.value = '修改已保存，你可以继续编辑或稍后提交审核。'
    }
  } catch (reason) {
    error.value = readableApiError(reason, '保存失败，请稍后重试。')
    if (savedItemId.value && !props.editId) warning.value = '文字信息已安全保存为服务器草稿；修正照片问题后再次提交，不会产生重复线索。'
  }
  finally { saving.value = false }
}

/**
 * 只有进入第 3 步后，发布表单才允许提交。
 * 这是发布流程的最后一道防线：即使以后某个地图或上传子组件误放了
 * submit 按钮，也不会在用户仍处于“时间地点”步骤时创建线索。
 */
function submitPublish() {
  if (step.value !== 3) {
    error.value = '地点已记录，请点击“下一步”完成确认后再提交。'
    return
  }
  void save(true)
}
</script>

<template>
  <div class="page publish-page">
    <header><h1 class="page-title">{{ isEditMode ? `编辑${activeKind === 'LOST' ? '遗失' : '招领'}线索` : activeKind === 'LOST' ? '发布遗失线索' : '登记拾获物品' }}</h1><p class="page-lead">公开信息用于检索，敏感信息仅用于核验。</p></header>
    <div class="stepper" aria-label="发布步骤"><button v-for="entry in [{n:1,t:'基本信息'},{n:2,t:'时间地点'},{n:3,t:'隐私与确认'}]" :key="entry.n" :class="{ active: step >= entry.n }" type="button" @click="goToStep(entry.n)"><span>{{ entry.n }}</span>{{ entry.t }}</button></div>
    <form class="panel publish-form" @submit.prevent="submitPublish">
      <section v-if="step === 1"><h2>描述这件物品</h2><div class="form-grid"><label class="wide"><span>标题 <i class="required-mark" aria-hidden="true">*</i></span><input v-model="form.title" required maxlength="120" placeholder="例如：黑色 Sony 入耳式耳机" /></label><label><span>类别 <i class="required-mark" aria-hidden="true">*</i></span><select v-model="form.category" required :disabled="metadataLoading"><option value="">{{ metadataLoading ? '读取中…' : '请选择' }}</option><option v-for="entry in categories" :key="entry.id" :value="String(entry.id)">{{ entry.name }}</option></select></label><label><span>颜色</span><input v-model="form.color" placeholder="可填写多色，如：黑色,银色" /></label><label><span>品牌</span><input v-model="form.brand" placeholder="未知时请留空，不猜测" /></label><label class="wide"><span>公开描述 <i class="required-mark" aria-hidden="true">*</i></span><textarea v-model="form.description" required maxlength="3000" rows="7" placeholder="外观、材质、型号等可公开特征。不要填写手机号、完整证件号或私密核验答案。"></textarea><small>{{ form.description.length }}/3000</small></label><div class="wide photo-field"><div class="photo-heading"><div><span>实拍照片（可选）</span><small>最多3张，单张不超过5MB；上传后自动压缩并移除定位信息。</small></div><button class="button button-ghost" type="button" :disabled="!photoSlotsLeft || processingPhotos" @click="fileInput?.click()">{{ processingPhotos ? '正在处理…' : photoSlotsLeft ? `选择照片（还可选${photoSlotsLeft}张）` : '已达3张上限' }}</button><input aria-label="选择发布照片" ref="fileInput" class="visually-hidden" type="file" accept="image/jpeg,image/png,image/webp" multiple @change="selectPhotos" /></div><div v-if="photos.length" class="photo-list"><article v-for="(photo,index) in photos" :key="photo.key" class="photo-card"><img :src="photo.url" :alt="`物品照片 ${index + 1}`"/><span v-if="index===0">封面</span><div><button type="button" :disabled="index===0" aria-label="向前移动" @click="movePhoto(index,-1)">←</button><button type="button" :disabled="index===photos.length-1" aria-label="向后移动" @click="movePhoto(index,1)">→</button><button class="remove" type="button" aria-label="删除照片" @click="removePhoto(index)">删除</button></div></article></div></div></div></section>
      <section v-else-if="step === 2">
        <h2>事件发生在何时何地</h2>
        <div class="form-grid">
          <label><span>{{ activeKind === 'LOST' ? '遗失时间' : '拾获时间' }} <i class="required-mark" aria-hidden="true">*</i></span><input v-model="form.occurred_at" required type="datetime-local" /></label>
          <label><span>公开地点 <i class="required-mark" aria-hidden="true">*</i></span><select v-model="form.location" required disabled><option v-if="!locations.length" value="">{{ metadataLoading || creatingRegion ? '正在读取当前校区…' : '暂无校区区域' }}</option><option v-for="entry in locations" :key="entry.id" :value="String(entry.id)">{{ entry.name }}</option></select></label>
          <div v-if="!metadataLoading && !locations.length" class="wide missing-location"><p>正在为当前校区建立公开区域。</p><button class="button button-ghost" type="button" :disabled="creatingRegion" @click="ensureCampusRegion">{{ creatingRegion ? '正在建立…' : '重新建立校区区域' }}</button></div>
          <label v-if="activeKind === 'FOUND'" class="wide"><span>保管服务站</span><select v-model="form.station"><option value="">暂未送站</option><option v-for="entry in stations" :key="entry.id" :value="String(entry.id)">{{ entry.name }} · {{statusLabel(entry.status)}}</option></select></label>
          <label class="wide"><span>补充位置说明（受保护，可选）</span><input v-model="form.location_detail" :placeholder="activeKind === 'LOST' ? '例如：可能在图书馆三楼至东门路线上' : '例如：图书馆三楼东侧自习区'" /></label>
        </div>
        <div class="privacy-callout"><AppIcon name="map" /><div><strong>{{ activeKind === 'LOST' ? '可能遗失地点' : '拾获地点' }}</strong><p v-if="activeKind === 'LOST'">可按可能性选择 1–5 个地点，也可留空。</p><p v-else>请选择实际拾获位置，精确信息仅用于核验。</p></div></div>
      </section>
      <section v-else><h2>{{ editingPublished ? '同步更新前确认' : '提交前确认' }}</h2><div class="review-card"><div><span>类型</span><strong>{{ activeKind === 'LOST' ? '遗失' : '招领' }}</strong></div><div><span>标题</span><strong>{{ form.title || '尚未填写' }}</strong></div><div><span>物品类别</span><strong>{{ selectedCategory?.name || '尚未选择' }}</strong></div><div><span>公开地点</span><strong>{{ selectedLocation?.name || '尚未选择' }}</strong></div><div><span>{{ activeKind === 'LOST' ? '可能遗失地点' : '拾获地点' }}（受保护）</span><strong>{{ protectedLocationSummary.length ? protectedLocationSummary.join(' → ') : '未知' }}</strong></div><div v-if="activeKind === 'FOUND'"><span>保管服务站</span><strong>{{ selectedStation?.name || '暂未送站' }}</strong></div><div><span>实拍照片</span><strong>{{ photos.length ? `${photos.length} 张（首张为封面）` : '未上传' }}</strong></div><div><span>公开描述</span><strong>{{ form.description ? `${form.description.length} 字` : '尚未填写' }}</strong></div></div><label class="consent"><input required type="checkbox" />我确认公开内容不含联系方式、完整证件号、私密核验答案，并同意内容通过安全检查后{{ editingPublished ? '同步到公开广场' : '提交审核' }}。<i class="required-mark" aria-hidden="true">*</i></label></section>
      <section v-if="step===2" class="protected-location-section">
        <h3>{{ activeKind === 'LOST' ? '可能遗失地点（受保护，最多 5 个）' : '拾获地点（受保护）' }}</h3>
        <AMapCampus pickable :selected-protected-location-ids="form.location_candidate_ids" :selected-coordinate-points="form.location_candidate_points" @pick="pickPoint" @select-protected-location="selectProtectedLocation"/>
        <div v-if="selectedCandidateCount" class="location-ranking" aria-label="已选受保护地点">
          <article v-for="(entry,index) in selectedProtectedLocations" :key="entry.id">
            <span>{{ activeKind === 'LOST' ? index === 0 ? '最可能' : `可能 ${index + 1}` : '拾获地点' }}</span><strong>{{ entry.name }}</strong>
            <div v-if="activeKind === 'LOST'"><button type="button" :disabled="index===0" aria-label="提高可能性排名" @click="moveProtectedLocation(index,-1)">↑</button><button type="button" :disabled="index===selectedProtectedLocations.length-1" aria-label="降低可能性排名" @click="moveProtectedLocation(index,1)">↓</button><button type="button" @click="removeProtectedLocation(entry.id)">移除</button></div>
          </article>
          <article v-for="(entry,index) in form.location_candidate_points" :key="`${entry.latitude}-${entry.longitude}`">
            <span>{{ activeKind === 'LOST' ? index === 0 ? '最可能' : `可能 ${index + 1}` : '拾获地点' }}</span>
            <strong>{{ entry.label }}<small>{{ entry.longitude.toFixed(6) }}，{{ entry.latitude.toFixed(6) }}</small></strong>
            <div><button v-if="activeKind === 'LOST'" type="button" :disabled="index===0" aria-label="提高可能性排名" @click="moveCoordinateLocation(index,-1)">↑</button><button v-if="activeKind === 'LOST'" type="button" :disabled="index===form.location_candidate_points.length-1" aria-label="降低可能性排名" @click="moveCoordinateLocation(index,1)">↓</button><button type="button" @click="removeCoordinateLocation(index)">移除</button></div>
          </article>
        </div>
        <p v-else class="location-empty">{{ activeKind === 'LOST' ? '不记得也没关系：保持未选即表示地点未知，系统会依据物品描述、类别、时间等其他证据匹配。' : '可点击地图中的校内区域记录拾获地点。' }}</p>
        <p v-if="form.location_candidate_points.length" class="coordinate-note">已选择 {{ form.location_candidate_points.length }} 个地图候选点，编号与上方可能性顺序一致；公开页面不会显示坐标。</p>
      </section>
      <p v-if="warning" class="form-message warning">{{ warning }}</p><p v-if="error" class="form-message error">{{ error }}</p><p v-if="success" class="form-message success">{{ success }}</p>
      <footer><button v-if="step > 1" class="button button-ghost" type="button" @click="step--">上一步</button><button class="button button-ghost" type="button" :disabled="saving" @click="isEditMode ? save(false) : saveLocalDraft()">{{ isEditMode ? '保存修改' : '保存草稿' }}</button><button v-if="step < 3" class="button button-brand" type="button" :disabled="metadataLoading" @click="nextStep">下一步 <AppIcon name="arrow" /></button><button v-else class="button button-brand" type="submit" :disabled="saving || metadataLoading">{{ saving ? '正在保存…' : editingPublished ? '保存并同步到广场' : isEditMode ? '保存并重新提交' : '提交审核' }}</button></footer>
    </form>
  </div>
</template>

<style scoped>
.publish-page { max-width: 980px; }.stepper { display: grid; grid-template-columns: repeat(3,1fr); margin: 40px 0 18px; }.stepper button { display: flex; align-items: center; gap: 9px; padding: 14px 0; color: var(--ct-text-muted); border: 0; border-bottom: 2px solid var(--ct-border); background: transparent; cursor: pointer; }.stepper button.active { color: var(--ct-text); border-color: var(--ct-brand); }.stepper span { display: grid; place-items: center; width: 26px; aspect-ratio: 1; border: 1px solid currentColor; border-radius: 50%; font-size: 11px; }.publish-form { padding: 34px; }.publish-form h2 { margin: 0 0 26px; }.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }.form-grid .wide { grid-column: 1/-1; }.form-grid label span,.photo-heading span { display: block; margin-bottom: 8px; color: var(--ct-text-muted); font-size: 13px; }.form-grid input,.form-grid textarea,.form-grid select { width: 100%; padding: 13px 14px; color: var(--ct-text); border: 1px solid var(--ct-border); border-radius: 11px; outline: 0; background: var(--ct-bg-soft); }.form-grid input:focus,.form-grid textarea:focus,.form-grid select:focus { border-color: var(--ct-brand); }.form-grid small { display: block; margin-top: 6px; color: var(--ct-text-muted); text-align: right; }.photo-field{padding:18px;border:1px solid var(--ct-border);border-radius:14px;background:var(--ct-bg-soft)}.photo-heading{display:flex;align-items:center;justify-content:space-between;gap:20px}.photo-heading small{max-width:560px;text-align:left;line-height:1.6}.photo-list{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:16px}.photo-card{position:relative;overflow:hidden;border:1px solid var(--ct-border);border-radius:12px;background:var(--ct-surface)}.photo-card img{display:block;width:100%;height:145px;object-fit:cover}.photo-card>span{position:absolute;top:8px;left:8px;padding:4px 7px;border-radius:6px;background:var(--ct-brand);color:var(--ct-brand-ink);font-size:10px}.photo-card>div{display:grid;grid-template-columns:auto auto 1fr;gap:5px;padding:8px}.photo-card button{padding:6px 9px;border:1px solid var(--ct-border);border-radius:7px;background:transparent;color:var(--ct-text);cursor:pointer}.photo-card button:disabled{opacity:.35}.photo-card .remove{justify-self:end;color:var(--ct-danger)}.photo-empty{margin:14px 0 0;color:var(--ct-text-muted);font-size:12px}.visually-hidden{position:absolute!important;width:1px!important;height:1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important}.missing-location { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 14px 16px; border: 1px dashed var(--ct-border); border-radius: 12px; }.missing-location p { margin: 0; color: var(--ct-text-muted); }.privacy-callout { display: flex; gap: 14px; margin-top: 24px; padding: 18px; color: var(--ct-info); border: 1px solid rgba(40,92,75,.25); border-radius: 14px; background: rgba(40,92,75,.06); }.privacy-callout p { margin: 4px 0 0; color: var(--ct-text-muted); }.protected-location-section{margin-top:22px}.protected-location-section>h3{margin:0 0 14px}.location-empty{margin:14px 0 0;padding:15px 17px;border:1px dashed var(--ct-border);border-radius:12px;color:var(--ct-text-muted);line-height:1.7}.location-ranking{display:grid;gap:8px;margin-top:14px}.location-ranking article{display:grid;grid-template-columns:76px 1fr auto;align-items:center;gap:12px;padding:12px 14px;border:1px solid var(--ct-border);border-radius:11px;background:var(--ct-bg-soft)}.location-ranking article>span{color:var(--ct-brand);font-size:12px}.location-ranking article>div{display:flex;gap:6px}.location-ranking button{padding:5px 8px;border:1px solid var(--ct-border);border-radius:7px;background:var(--ct-surface);color:var(--ct-text);cursor:pointer}.location-ranking button:disabled{opacity:.35;cursor:default}.review-card { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; overflow: hidden; border: 1px solid var(--ct-border); border-radius: 14px; background: var(--ct-border); }.review-card div { display: flex; flex-direction: column; gap: 9px; padding: 18px; background: var(--ct-bg-soft); }.review-card span { color: var(--ct-text-muted); font-size: 12px; }.consent { display: flex; gap: 10px; margin: 24px 0; color: var(--ct-text-muted); line-height: 1.6; }.publish-form footer { display: flex; justify-content: flex-end; gap: 10px; margin-top: 30px; padding-top: 22px; border-top: 1px solid var(--ct-border); }.form-message { padding: 12px; border-radius: 10px; }.form-message.warning { color: #835d12; background: rgba(192,139,28,.1); }.form-message.error { color: var(--ct-danger); background: rgba(173,52,52,.08); }.form-message.success { color: var(--ct-success); background: rgba(54,100,75,.08); }
.location-ranking strong small{display:block;margin-top:4px;color:var(--ct-text-muted);font-size:11px;font-weight:400}.coordinate-note{margin:12px 0 0;color:var(--ct-text-muted);font-size:12px}
.required-mark{margin-left:3px;color:var(--ct-danger);font-style:normal;font-weight:800}
@media (max-width: 620px) { .form-grid,.review-card,.photo-list { grid-template-columns: 1fr; }.form-grid .wide { grid-column: auto; }.publish-form { padding: 22px; }.stepper button { align-items: flex-start; flex-direction: column; }.photo-heading{align-items:flex-start;flex-direction:column}.photo-card img{height:200px}.location-ranking article{grid-template-columns:1fr}.location-ranking article>div{justify-content:flex-start} }
</style>
