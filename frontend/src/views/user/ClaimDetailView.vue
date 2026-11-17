<script setup lang="ts">
import {readableApiError} from '../../api/client'
import {statusLabel} from '../../utils/statusLabels'
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api, ApiError } from '../../api/client'

type Event = { id:number; actor_name:string; from_status:string; to_status:string; note:string; created_at:string }
type Appointment = { station_id:number; scheduled_at:string }
type Claim = {
  id:string; found_item_id:string; item_title:string; statement:string; evidence:Record<string,string>
  status:string; decision_note:string; events:Event[]; appointment?:Appointment; allowed_actions:string[]
  custody_mode:'STATION'|'FINDER'; viewer_role:'CLAIMANT'|'FINDER'|'STAFF'; conversation_id:number|null
  handover_method:''|'STATION'|'DIRECT'; claimant_confirmed_at:string|null; finder_confirmed_at:string|null
  custody_station:{id:number;name:string;address:string;phone:string;opening_hours:Record<string,string>}|null
}
type Station = { id:number; name:string }

const route = useRoute()
const claim = ref<Claim | null>(null)
const stations = ref<Station[]>([])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const success = ref('')
const decision = reactive({ decision:'APPROVE', note:'' })
const appointment = reactive({ station_id:'', scheduled_at:'' })
const oneTimeCode = ref('')

const canDecide = computed(() => claim.value?.allowed_actions.includes('decide'))
const canSchedule = computed(() => claim.value?.allowed_actions.includes('schedule_handover') && !claim.value?.appointment)
const canStartDirect = computed(() => claim.value?.allowed_actions.includes('start_direct_handover'))
const canConfirmDirect = computed(() => claim.value?.allowed_actions.includes('confirm_direct_handover'))
const canCompleteStationPickup = computed(() => claim.value?.allowed_actions.includes('complete_station_pickup'))
const reviewTitle = computed(() => claim.value?.viewer_role === 'FINDER' ? '核对认领申请' : '服务站审核')
const handoverNotice = computed(() => {
  if (claim.value?.viewer_role !== 'CLAIMANT') return ''
  if (claim.value.status === 'APPROVED' && claim.value.custody_station) return `遗失物品已在${claim.value.custody_station.name}，可前往领取，无需选择服务站或预约。`
  if (claim.value.status === 'APPROVED') return '认领申请已通过，请在下方选择交接方式。'
  if (claim.value.handover_method === 'STATION' && claim.value.status === 'HANDOVER_PENDING') {
    return claim.value.custody_station ? `遗失物品已在${claim.value.custody_station.name}，可前往领取。` : '服务站交接已安排。'
  }
  return ''
})

async function load() {
  try {
    const [claimResponse, stationResponse] = await Promise.all([
      api<{data:Claim}>(`/claims/${route.params.id}/`),
      api<{data:{items:Station[]}}>('/stations/?page_size=100'),
    ])
    claim.value = claimResponse.data
    stations.value = stationResponse.data.items
    appointment.station_id ||= String(stations.value[0]?.id ?? '')
  } catch (reason) {
    error.value = readableApiError(reason,'无法读取认领详情')
  } finally {
    loading.value = false
  }
}

async function decide() {
  if (!claim.value) return
  await runAction(
    () => api(`/claims/${claim.value!.id}/decision/`, { method:'POST', body:JSON.stringify(decision) }),
    '处理结果已保存',
  )
}

async function startDirect() {
  if (!claim.value) return
  await runAction(
    () => api(`/claims/${claim.value!.id}/direct-handover/`, { method:'POST' }),
    '已开启直接交接，请在站内消息中联系对方',
  )
}

async function confirmDirect() {
  if (!claim.value) return
  await runAction(
    () => api(`/claims/${claim.value!.id}/direct-handover/confirm/`, { method:'POST' }),
    '你的交接确认已保存',
  )
}

async function completeStationPickup() {
  if (!claim.value) return
  await runAction(
    () => api(`/claims/${claim.value!.id}/station-pickup/complete/`, { method:'POST' }),
    '服务站领取已确认完成',
  )
}

async function schedule() {
  if (!claim.value) return
  await runAction(async () => {
    const response = await api<{data:{one_time_code:string}}>(`/claims/${claim.value!.id}/appointment/`, {
      method:'POST',
      body:JSON.stringify({ station_id:appointment.station_id, scheduled_at:new Date(appointment.scheduled_at).toISOString() }),
    })
    oneTimeCode.value = response.data.one_time_code
  }, '预约已创建')
}

async function runAction(action:() => Promise<unknown>, message:string) {
  busy.value = true
  error.value = ''
  success.value = ''
  try {
    await action()
    success.value = message
    await load()
  } catch (reason) {
    error.value = readableApiError(reason,'操作失败')
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page detail">
    <p v-if="loading" class="empty">正在读取…</p>
    <p v-else-if="error && !claim" class="empty error">{{ error }}</p>
    <template v-else-if="claim">
      <header><h1 class="page-title">{{ claim.item_title }}</h1><span class="status-large">{{statusLabel(claim.status)}}</span></header>
      <p v-if="error" class="notice error">{{ error }}</p>
      <p v-if="success" class="notice success">{{ success }}</p>
      <p v-if="handoverNotice" class="notice success">{{ handoverNotice }}</p>

      <section class="detail-grid">
        <div class="panel timeline">
          <h2>处理记录</h2>
          <ol><li v-for="entry in claim.events" :key="entry.id"><i></i><div><strong>{{ entry.to_status }}</strong><span>{{ entry.actor_name || '系统' }} · {{ new Date(entry.created_at).toLocaleString('zh-CN') }}</span><p v-if="entry.note">{{ entry.note }}</p></div></li></ol>
        </div>

        <aside>
          <section class="panel summary">
            <h2>核验信息</h2>
            <p>{{ claim.evidence.verification_detail || claim.statement }}</p>
            <p v-if="claim.decision_note">处理备注：{{ claim.decision_note }}</p>
            <RouterLink :to="`/items/${claim.found_item_id}`">查看招领信息</RouterLink>
          </section>

          <form v-if="canDecide" class="panel action" @submit.prevent="decide">
            <h2>{{ reviewTitle }}</h2>
            <select v-model="decision.decision"><option value="APPROVE">确认信息相符</option><option value="NEEDS_INFO">请对方补充</option><option value="REJECT">信息不符</option></select>
            <textarea v-model="decision.note" placeholder="备注（可选）" />
            <button class="button button-brand" :disabled="busy">提交</button>
          </form>

          <section v-if="claim.viewer_role === 'CLAIMANT' && claim.custody_station && ['APPROVED','HANDOVER_PENDING'].includes(claim.status)" class="panel station-pickup">
            <h2>前往服务站领取</h2>
            <strong>{{ claim.custody_station.name }}</strong>
            <p>{{ claim.custody_station.address || '请按服务站页面公布的位置前往' }}</p>
            <p v-if="claim.custody_station.phone">联系电话：{{ claim.custody_station.phone }}</p>
            <p>物品已由该服务站保管，可直接前往领取，无需重新选择站点或预约时间。</p>
          </section>

          <section v-if="canCompleteStationPickup && claim.custody_station" class="panel station-pickup">
            <h2>确认现场领取</h2>
            <strong>{{ claim.custody_station.name }}</strong>
            <p>请现场核对认领人身份与物品信息，交付后直接确认完成。</p>
            <button class="button button-brand" :disabled="busy" @click="completeStationPickup">确认已领取</button>
          </section>

          <section v-if="(canStartDirect || canSchedule) && !claim.custody_station" class="panel choices">
            <h2>选择交接方式</h2>
            <button v-if="canStartDirect" class="button button-brand" :disabled="busy" @click="startDirect">联系对方直接交接</button>
            <p v-if="canSchedule&&!stations.length">当前校区暂无经核验的官方服务站。可选择直接交接，并在站内消息中约定图书馆门口、学生服务中心门口等公共见面地点；这些地点不承担物品保管或身份核验。</p>
            <form v-if="canSchedule&&stations.length" class="station-form" @submit.prevent="schedule">
              <select v-model="appointment.station_id" required><option v-for="station in stations" :key="station.id" :value="station.id">{{ station.name }}</option></select>
              <input v-model="appointment.scheduled_at" required type="datetime-local" />
              <button class="button button-ghost" :disabled="busy">预约服务站</button>
            </form>
          </section>

          <section v-if="claim.handover_method === 'DIRECT'" class="panel direct">
            <h2>直接交接</h2>
            <div class="confirm-state"><span :class="{done:claim.finder_confirmed_at}">拾取者{{ claim.finder_confirmed_at ? '已确认' : '待确认' }}</span><span :class="{done:claim.claimant_confirmed_at}">认领人{{ claim.claimant_confirmed_at ? '已确认' : '待确认' }}</span></div>
            <RouterLink v-if="claim.conversation_id" :to="`/messages/${claim.conversation_id}`" class="button button-ghost">联系对方</RouterLink>
            <button v-if="canConfirmDirect" class="button button-brand" :disabled="busy" @click="confirmDirect">确认已完成交接</button>
          </section>

          <section v-if="oneTimeCode && !claim.custody_station" class="code"><span>交接码</span><strong>{{ oneTimeCode }}</strong></section>
        </aside>
      </section>
    </template>
  </div>
</template>

<style scoped>
.detail header{display:flex;justify-content:space-between;align-items:end;gap:25px}.status-large{padding:12px 18px;color:var(--ct-brand);border:1px solid var(--ct-border-strong);border-radius:13px}.notice{padding:12px;border-radius:10px}.notice.error{color:var(--ct-danger);background:rgba(173,52,52,.07)}.notice.success{color:var(--ct-success);background:rgba(54,100,75,.07)}.detail-grid{display:grid;grid-template-columns:1fr 390px;gap:18px;margin-top:34px}.timeline,.summary,.action,.choices,.direct,.station-pickup{padding:25px;box-shadow:none}.timeline h2,.summary h2,.action h2,.choices h2,.direct h2,.station-pickup h2{margin:0 0 22px}.station-pickup{display:grid;gap:10px}.station-pickup strong{color:var(--ct-success);font-size:20px}.station-pickup p{margin:0;color:var(--ct-text-muted);line-height:1.7}.timeline ol{margin:0;padding:0;list-style:none}.timeline li{display:grid;grid-template-columns:20px 1fr;gap:12px;min-height:90px}.timeline i{position:relative;width:10px;height:10px;margin-top:5px;border-radius:50%;background:var(--ct-brand)}.timeline i:after{position:absolute;top:15px;bottom:-70px;left:4px;width:1px;background:var(--ct-border);content:''}.timeline li:last-child i:after{display:none}.timeline span{display:block;margin-top:5px;color:var(--ct-text-muted);font-size:12px}.timeline p,.summary p{color:var(--ct-text-muted)}.summary>a{color:var(--ct-brand)}aside{display:grid;align-content:start;gap:12px}.action,.choices,.direct,.station-form{display:grid;gap:12px}.action select,.action textarea,.station-form select,.station-form input{width:100%;padding:12px;color:var(--ct-text);border:1px solid var(--ct-border);border-radius:10px;background:var(--ct-bg-soft)}.action textarea{min-height:72px}.station-form{padding-top:14px;border-top:1px solid var(--ct-border)}.confirm-state{display:grid;grid-template-columns:1fr 1fr;gap:8px}.confirm-state span{padding:10px;border-radius:8px;background:var(--ct-bg-soft);text-align:center}.confirm-state .done{color:var(--ct-success)}.code{padding:18px;color:var(--ct-brand);border:1px solid var(--ct-border-strong);border-radius:14px;text-align:center}.code span{display:block}.code strong{display:block;margin:8px;font:800 30px monospace;letter-spacing:.2em}.handover{justify-content:center}.empty{display:grid;place-items:center;min-height:320px}.error{color:var(--ct-danger)}@media(max-width:850px){.detail-grid{grid-template-columns:1fr}.detail header{align-items:start;flex-direction:column}}
</style>
