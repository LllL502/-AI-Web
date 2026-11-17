// Negative, quoted and hypothetical input must never imply consent.
import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,expect,it,vi} from 'vitest'
import Panel,{type AgentTask} from '../../src/components/AgentTaskPanel.vue'
const mocks=vi.hoisted(()=>({api:vi.fn()}))
vi.mock('../../src/api/client',()=>({api:mocks.api,readableApiError:()=> '暂未完成'}))
const task:AgentTask={stage:'results',description:'本子',reply:'已检索',candidates:[{id:'found',title:'本子',description:'A4',category_id:1,location:'教学楼',color:'蓝色',brand:''}],owned_lost:[{id:'lost',title:'我的本子',category_id:1}]}
beforeEach(()=>{mocks.api.mockReset()})

it('never submits a claim from negated, quoted or hypothetical text',async()=>{
 mocks.api.mockResolvedValue({data:{claim:{id:'claim',status:'SUBMITTED',item_title:'本子',allowed_actions:[]}}})
 const wrapper=mount(Panel,{props:{task}})
 wrapper.vm.handleIntent('看看第1个')
 wrapper.vm.handleIntent('核验特征：第三页有一个特别的标记')
 for(const text of ['先不要提交认领','可以提交认领吗？','如果提交认领会怎样','他说“确认提交认领”','不确认提交认领'])wrapper.vm.handleIntent(text)
 await flushPromises()
 expect(mocks.api).not.toHaveBeenCalled()
 wrapper.unmount()
})

for(const scenario of [
 {key:'negated_receipt',input:'我还没收到物品',allowed:'confirm_direct_handover',action:'confirm_handover'},
 {key:'negated_handover_choice',input:'不要选择直接交接',allowed:'start_direct_handover',action:'start_handover'},
])it('requires explicit consent for '+scenario.key,async()=>{
 const claim={id:'claim1',status:'HANDOVER_PENDING',item_title:'测试物品',allowed_actions:[scenario.allowed],viewer_role:'CLAIMANT'}
 mocks.api.mockImplementation(async(path:string)=>path.startsWith('/claims/?')?{data:{items:[claim]}}:{data:{claim}})
 const wrapper=mount(Panel,{props:{task}})
 await wrapper.findAll('button').find(button=>button.text()==='继续已有认领')!.trigger('click')
 await flushPromises()
 await wrapper.findAll('button').find(button=>button.text().includes('测试物品 ·'))!.trigger('click')
 await flushPromises()
 mocks.api.mockClear()
 for(const text of [scenario.input,'我还没有拿到实物','如果我收到物品怎么办？','他说“确认选择直接交接”'])wrapper.vm.handleIntent(text)
 await flushPromises()
 expect(mocks.api).not.toHaveBeenCalled()
 const positive=scenario.action==='confirm_handover'?'我已拿到实物，确认我的交接':'确认选择双方直接交接'
 wrapper.vm.handleIntent(positive)
 await flushPromises()
 const body=JSON.parse(mocks.api.mock.calls[0][1].body)
 expect(body.action).toBe(scenario.action);expect(body.confirmed).toBe(true)
 wrapper.unmount()
})
