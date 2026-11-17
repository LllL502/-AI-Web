import {mount,flushPromises} from '@vue/test-utils'
import {beforeEach,expect,it,vi} from 'vitest'
import ConfigView from '../../src/views/admin/AlgorithmConfigView.vue'
import Readiness from '../../src/components/ServiceReadiness.vue'
const mocks=vi.hoisted(()=>({api:vi.fn()}))
vi.mock('../../src/api/client',()=>({api:mocks.api,readableApiError:()=> '保存失败'}))
beforeEach(()=>{mocks.api.mockReset()})
const historical={id:1,name:'历史参数',version:'v1',weights:{text:.5,category:.15,location:.12,time:.1,color:.08,brand:.05},thresholds:{min_score:.4},preprocessing:{aliases:{校图:'图书馆'}},state:'HISTORICAL',editable:false,is_published:false}
it('copies frozen configuration into a new draft and never edits the source',async()=>{
 mocks.api.mockResolvedValue({data:{items:[historical]}})
 const wrapper=mount(ConfigView)
 await flushPromises()
 expect(wrapper.text()).toContain('历史已发布')
 expect(wrapper.findAll('button').some(button=>button.text()==='编辑草稿')).toBe(false)
 await wrapper.findAll('button').find(button=>button.text()==='基于此版本新建')!.trigger('click')
 const inputs=wrapper.findAll('input')
 await inputs[1]!.setValue('v2')
 await wrapper.get('form').trigger('submit')
 await flushPromises()
 const write=mocks.api.mock.calls.find(call=>call[1]?.method==='POST')!
 expect(write[0]).toBe('/admin/matching-configs/')
 const body=JSON.parse(write[1].body)
 expect(body.version).toBe('v2');expect(body.thresholds.min_score).toBe(.4)
 expect(body.preprocessing.aliases).toEqual({校图:'图书馆'})
 expect(mocks.api.mock.calls.some(call=>call[1]?.method==='PATCH')).toBe(false)
 wrapper.unmount()
})
it('renders a speech outage independently of other ready models',async()=>{
 mocks.api.mockResolvedValue({data:{models:{extraction:{state:'available',ready:true},embedding:{state:'available',ready:true},vision:{state:'available',ready:true},voice:{state:'unavailable',ready:false}}}})
 const wrapper=mount(Readiness)
 await flushPromises()
 expect(wrapper.text()).toContain('小寻童声')
 expect(wrapper.text()).toContain('服务未启动')
 expect(wrapper.findAll('.offline')).toHaveLength(1)
 wrapper.unmount()
})
