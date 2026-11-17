import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import Panel, {type AgentTask} from '../../src/components/AgentTaskPanel.vue'
const mocks=vi.hoisted(()=>({api:vi.fn()}))
vi.mock('../../src/api/client',()=>({api:mocks.api,readableApiError:()=> '暂未完成'}))
const task:AgentTask={stage:'results',description:'粉色本子',reply:'已检索',candidates:[{id:'found',title:'粉色本子',description:'A4大小',category_id:1,location:'教学楼',color:'粉色',brand:''}],publication:{kind:'LOST',title:'遗失本子',description:'粉色A4本子',category:1,location:2,occurred_at:'',color:'粉色',brand:''},options:{categories:[{id:1,name:'纸质笔记本'}],locations:[{id:2,name:'教学楼'}]},owned_lost:[{id:'lost',title:'我的本子',category_id:1}]}
beforeEach(()=>{mocks.api.mockReset()})

it('selects a candidate by chat intent and sends claim only with explicit confirmation',async()=>{
  const wrapper=mount(Panel,{props:{task}})
  expect(wrapper.vm.handleIntent('我想看看第1个')?.reply).toContain('粉色本子')
  expect(wrapper.vm.handleIntent('核验特征：第三页写着一行只有我知道的字')?.reply).toContain('私密')
  await flushPromises()
  expect(mocks.api).not.toHaveBeenCalled()
  mocks.api.mockResolvedValue({data:{claim:{id:'claim',status:'SUBMITTED',item_title:'粉色本子',allowed_actions:[]},message:'已提交'}})
  wrapper.vm.handleIntent('确认提交认领')
  await flushPromises()
  const body=JSON.parse(mocks.api.mock.calls[0][1].body)
  expect(body.action).toBe('claim');expect(body.confirmed).toBe(true)
  expect(body.payload.related_lost_item_id).toBe('lost')
  expect(body.payload.statement).toContain('第三页')
  expect(wrapper.text()).toContain('等待对方核验')
  wrapper.unmount()
})

it('requires missing event time and never silently invents it for publication',async()=>{
  const wrapper=mount(Panel,{props:{task}})
  wrapper.vm.handleIntent('帮我发布寻物信息');await flushPromises()
  await wrapper.get('.agent-publication').trigger('submit')
  await flushPromises()
  expect(mocks.api).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('还需要确认')
  wrapper.unmount()
})

it('captures private proof even before selecting a candidate instead of sending it to the general model',()=>{
  const wrapper=mount(Panel,{props:{task}})
  expect(wrapper.vm.handleIntent('核验特征：第三页有我的学号')?.reply).toContain('不会把它放进公开描述')
  expect(mocks.api).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('can resume, book a station, verify its code and confirm only the claimant side',async()=>{
  const record={id:'claim-station',status:'APPROVED',item_title:'可预约耳机',allowed_actions:['schedule_handover'],viewer_role:'CLAIMANT'}
  let current:Record<string,unknown>={...record}
  mocks.api.mockImplementation(async(path:string,options?:RequestInit)=>{
    if(path.startsWith('/claims/?'))return {data:{items:[record]}}
    if(path==='/stations/')return {data:{items:[{id:2,name:'图书馆服务站'}]}}
    if(path.endsWith('/handover/verify/'))return {data:{verified_at:'2030-01-01T12:00:00Z',claimant_confirmed_at:null}}
    const body=JSON.parse(options!.body as string)
    if(body.action==='schedule')current={...record,status:'HANDOVER_PENDING',allowed_actions:[],appointment:{verified_at:null,claimant_confirmed_at:null}}
    if(body.action==='confirm_station_handover')current={...current,appointment:{verified_at:'2030-01-01T12:00:00Z',claimant_confirmed_at:'2030-01-01T12:05:00Z'}}
    return {data:{claim:current,...(body.action==='schedule'?{one_time_code:'123456'}:{})}}
  })
  const wrapper=mount(Panel,{props:{task}})
  const click=async(text:string)=>{await wrapper.findAll('button').find(b=>b.text()===text)!.trigger('click');await flushPromises()}
  await click('继续已有认领')
  await click('可预约耳机 · 认领已通过')
  await click('帮我预约服务站')
  await wrapper.get('[aria-label="预约服务站"]').setValue('2')
  await wrapper.get('[aria-label="预约时间"]').setValue('2030-01-01T14:00')
  await wrapper.get('.agent-claim-progress form').trigger('submit');await flushPromises()
  expect(wrapper.text()).toContain('123456')
  await wrapper.get('.agent-claim-progress input').setValue('123456')
  await wrapper.get('.agent-claim-progress form').trigger('submit');await flushPromises()
  expect(mocks.api.mock.calls.some(call=>call[0]==='/claims/claim-station/handover/verify/')).toBe(true)
  await click('已拿到实物，确认我的服务站交接')
  expect(wrapper.text()).toContain('等待实物交接')
  wrapper.unmount()
})

it('reads and explicitly sends messages through the actual website messaging endpoint',async()=>{
  const record={id:'claim-message',status:'APPROVED',item_title:'可沟通耳机',allowed_actions:[],viewer_role:'CLAIMANT',conversation_id:7}
  mocks.api.mockImplementation(async(path:string,options?:RequestInit)=>{
    if(path.startsWith('/claims/?'))return {data:{items:[record]}}
    if(path==='/messages/7/')return {data:{messages:[{id:1,body:'可以到图书馆核对',sender_name:'拾得者'}]}}
    if(path==='/messages/7/messages/')return {data:{id:2}}
    expect(JSON.parse(options!.body as string).action).toBe('status')
    return {data:{claim:record}}
  })
  const wrapper=mount(Panel,{props:{task}})
  const click=async(text:string)=>{await wrapper.findAll('button').find(b=>b.text()===text)!.trigger('click');await flushPromises()}
  await click('继续已有认领');await click('可沟通耳机 · 认领已通过')
  expect(wrapper.text()).toContain('可以到图书馆核对')
  expect(mocks.api.mock.calls.some(call=>call[0]==='/messages/7/messages/')).toBe(false)
  await wrapper.get('.agent-claim-progress textarea').setValue('我下午到图书馆核对')
  await wrapper.get('.agent-claim-progress form').trigger('submit');await flushPromises()
  const sent=mocks.api.mock.calls.find(call=>call[0]==='/messages/7/messages/')!
  expect(JSON.parse(sent[1].body).body).toBe('我下午到图书馆核对')
  wrapper.unmount()
})


it('natural rejection excludes a candidate instead of selecting it',async()=>{
 const wrapper=mount(Panel,{props:{task}})
 const reply=wrapper.vm.handleIntent('第一个不是我的')
 expect(reply?.reply).toContain('排除')
 expect(wrapper.emitted('exclude')?.[0]).toEqual(['found'])
 expect(wrapper.find('.agent-selected').exists()).toBe(false)
 wrapper.unmount()
})

it('prepares publication from a planned action and exposes no private proof as context',async()=>{
 const wrapper=mount(Panel,{props:{task}})
 wrapper.vm.applyAssistantAction({type:'publish'});await flushPromises()
 expect(wrapper.find('.agent-publication').exists()).toBe(true)
 expect(mocks.api).not.toHaveBeenCalled()
 wrapper.vm.handleIntent('核验特征：第三页有我的学号')
 expect(JSON.stringify(wrapper.vm.getToolContext())).not.toContain('学号')
 wrapper.vm.resetSession();await flushPromises()
 expect(wrapper.find('.agent-publication').exists()).toBe(false)
 wrapper.unmount()
})


it('submits up to five ranked locations through the existing item protocol',async()=>{
 const places=Array.from({length:6},(_,i)=>({id:i+10,name:'地点'+i}))
 const enriched={...task,publication:{...task.publication!,occurred_at:'2026-11-15T14:00',location_candidate_ids:[]},options:{...task.options!,candidate_locations:places}}
 const wrapper=mount(Panel,{props:{task:enriched}})
 wrapper.vm.applyAssistantAction({type:'publish'});await flushPromises()
 const click=async(text:string)=>{await wrapper.findAll('button').find(b=>b.text()===text)!.trigger('click');await flushPromises()}
 for(const p of places.slice(0,5))await click(p.name)
 await click(places[5]!.name)
 expect(wrapper.findAll('.location-ranking li')).toHaveLength(5)
 expect(wrapper.text()).toContain('最多选择5个')
 await wrapper.findAll('button[aria-label="提高地点可能性排名"]')[1]!.trigger('click')
 mocks.api.mockResolvedValue({data:{item:{id:'published',title:'本子',category_id:1,review_status:'APPROVED'}}})
 await wrapper.get('.agent-publication').trigger('submit');await flushPromises()
 const sent=JSON.parse(mocks.api.mock.calls[0][1].body)
 expect(sent.payload.location_candidate_ids).toEqual([11,10,12,13,14])
 wrapper.unmount()
})


it('prefills only the known day and publishes found information after confirmed clock',async()=>{
 const wrapper=mount(Panel,{props:{task:{...task,publication:{...task.publication!,kind:'FOUND',title:'拾到蓝色笔袋',occurred_date:'2026-11-16'}}}})
 wrapper.vm.handleIntent('帮我发布招领信息');await flushPromises()
 expect((wrapper.get('[aria-label="事件日期"]').element as HTMLInputElement).value).toBe('2026-11-16')
 expect((wrapper.get('[aria-label="具体时间"]').element as HTMLInputElement).value).toBe('')
 await wrapper.get('.agent-publication').trigger('submit');await flushPromises()
 expect(mocks.api).not.toHaveBeenCalled()
 mocks.api.mockResolvedValue({data:{item:{id:'found-new',title:'拾到蓝色笔袋',category_id:1,review_status:'APPROVED'}}})
 await wrapper.get('[aria-label="具体时间"]').setValue('21:00')
 await wrapper.get('.agent-publication').trigger('submit');await flushPromises()
 const body=JSON.parse(mocks.api.mock.calls[0][1].body)
 expect(body.payload.kind).toBe('FOUND')
 expect(body.payload.occurred_at).toBe(new Date('2026-11-16T21:00').toISOString())
 expect(body.payload).not.toHaveProperty('occurred_date')
 wrapper.unmount()
})

it('sends a change to found publication back to the assistant instead of opening a stale lost draft',()=>{
 const wrapper=mount(Panel,{props:{task}})
 expect(wrapper.vm.handleIntent('帮我发布招领信息')).toBeNull()
 expect(wrapper.find('.agent-publication').exists()).toBe(false)
 wrapper.unmount()
})


it('fills new conversational details into an open preview while preserving an edited title',async()=>{
 const wrapper=mount(Panel,{props:{task}})
 wrapper.vm.handleIntent('帮我发布寻物信息');await flushPromises()
 await wrapper.get('input[maxlength="120"]').setValue('我自己修改过的标题')
 await wrapper.setProps({task:{...task,publication:{...task.publication!,occurred_date:'2026-11-16',occurred_at:'2026-11-16T21:00'}}});await flushPromises()
 expect((wrapper.get('[aria-label="事件日期"]').element as HTMLInputElement).value).toBe('2026-11-16')
 expect((wrapper.get('[aria-label="具体时间"]').element as HTMLInputElement).value).toBe('21:00')
 expect((wrapper.get('input[maxlength="120"]').element as HTMLInputElement).value).toBe('我自己修改过的标题')
 wrapper.unmount()
})


it('attaches selected photos to the confirmed publication and clears them only after success',async()=>{
 const file=new File(['photo'],'photo.png',{type:'image/png'})
 const wrapper=mount(Panel,{props:{task:{...task,publication:{...task.publication!,kind:'FOUND',occurred_at:'2026-11-16T21:30'}},photos:[{key:'photo-key',file,url:'blob:photo'}]}})
 mocks.api.mockResolvedValue({data:{item:{id:'photo-publication',title:'拾到本子',category_id:1,review_status:'APPROVED'}}})
 wrapper.vm.handleIntent('帮我发布招领信息');await flushPromises()
 await wrapper.get('.agent-publication').trigger('submit');await flushPromises()
 const form=mocks.api.mock.calls[0][1].body as FormData
 expect(form).toBeInstanceOf(FormData);expect(form.getAll('photos')).toHaveLength(1)
 expect(JSON.parse(form.get('payload') as string).kind).toBe('FOUND')
 expect(wrapper.emitted('published')).toHaveLength(1)
 wrapper.unmount()
})

it('shows authorized finder proof separately and submits the explicitly confirmed decision',async()=>{
 const record={id:'finder-claim',status:'SUBMITTED',item_title:'蓝色耳机',viewer_role:'FINDER',allowed_actions:['decide'],statement:'盒盖的私密划痕'}
 mocks.api.mockImplementation(async(path:string,options?:RequestInit)=>{
  if(path.startsWith('/claims/?'))return {data:{items:[record]}}
  if(path==='/claims/finder-claim/')return {data:record}
  const body=JSON.parse(options!.body as string)
  return {data:{claim:{...record,status:body.action==='decide'?'NEEDS_INFO':'SUBMITTED'}}}
 })
 const wrapper=mount(Panel,{props:{task}})
 await wrapper.findAll('button').find(b=>b.text()==='处理收到的认领')!.trigger('click');await flushPromises()
 await wrapper.findAll('button').find(b=>b.text().includes('蓝色耳机 ·'))!.trigger('click');await flushPromises()
 expect(wrapper.text()).toContain('盒盖的私密划痕')
 expect(wrapper.vm.getToolContext()).toEqual({claim_id:'finder-claim'})
 const form=wrapper.findAll('form').find(form=>form.text().includes('核验认领材料'))!
 await form.get('textarea').setValue('请补充盒盖细节照片')
 await form.trigger('submit');await flushPromises()
 const action=mocks.api.mock.calls.filter(call=>call[0]==='/assistant/agent/actions/').map(call=>JSON.parse(call[1].body)).find(body=>body.action==='decide')
 expect(action.confirmed).toBe(true);expect(action.payload.decision).toBe('NEEDS_INFO')
 expect(action.payload.note).toBe('请补充盒盖细节照片')
 wrapper.unmount()
})
