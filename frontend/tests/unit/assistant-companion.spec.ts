import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import Companion from '../../src/components/AssistantCompanion.vue'
import { useAuthStore } from '../../src/stores/auth'
const mocks = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../../src/api/client', () => ({ api: mocks.api, readableApiError: () => '服务暂不可用' }))
vi.mock('vue-router', () => ({ RouterLink: { template: '<a><slot /></a>' } }))
beforeEach(() => { mocks.api.mockReset(); setActivePinia(createPinia()) })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); document.body.innerHTML = '' })
function mountAgent() {
  useAuthStore().user = { id: 1, username: 'student', display_name: '同学', email: '', role: 'USER' }
  return mount(Companion, { attachTo: document.body, props: { mode: 'text', description: '' } })
}

it('fills grounded description and presents tool results inside chat', async () => {
  mocks.api.mockResolvedValue({ data: { reply: '已检索到线索', description: '黑色耳机', stage: 'results', candidates: [{id:'candidate',title:'找到黑色耳机',description:'黑色',category_id:1,location:'图书馆',color:'黑色',brand:''}] } })
  const wrapper = mountAgent()
  await wrapper.get('.agent-character').trigger('click')
  const textarea = document.querySelector('textarea')!
  textarea.value = '黑色耳机'; textarea.dispatchEvent(new Event('input', { bubbles: true }))
  document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  expect(mocks.api.mock.calls[0][0]).toBe('/assistant/conversation/')
  expect(wrapper.emitted('apply')?.[0]).toEqual(['黑色耳机'])
  expect(document.body.textContent).toContain('找到黑色耳机')
  expect(document.body.textContent).toContain('查看并核对这件物品')
  expect(document.querySelector('.chat-continue')).toBeNull()
  wrapper.unmount()
})

it('does not overwrite a description edited during inference', async () => {
  let resolve!: (value: unknown) => void
  mocks.api.mockReturnValue(new Promise(r => { resolve = r }))
  const wrapper = mountAgent()
  await wrapper.get('.agent-character').trigger('click')
  const textarea = document.querySelector('textarea')!
  textarea.value = '耳机'; textarea.dispatchEvent(new Event('input', { bubbles: true }))
  document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  await wrapper.setProps({ description: '我手动修改了线索' })
  resolve({ data: { reply: '好的', description: '耳机' } }); await flushPromises()
  expect(wrapper.emitted('apply')).toBeUndefined()
  expect(wrapper.props('description')).toBe('我手动修改了线索')
  wrapper.unmount()
})

it('does not call inference before a guest logs in', async () => {
  const wrapper = mount(Companion, { props: { mode: 'text', description: '' } })
  await wrapper.get('.agent-character').trigger('click')
  expect(document.body.textContent).toContain('登录后和小寻交流')
  expect(mocks.api).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('cycles gestures every 20 seconds while keeping bubbles on the original 55 second interval',async()=>{
  vi.useFakeTimers()
  vi.stubGlobal('matchMedia',()=>({matches:false}))
  const wrapper=mountAgent()
  await flushPromises()
  expect(wrapper.get('.agent-character .xun-agent').classes()).toContain('wave')
  expect(wrapper.find('.agent-bubble').exists()).toBe(true)
  await vi.advanceTimersByTimeAsync(7000)
  expect(wrapper.get('.agent-character .xun-agent').classes()).toContain('idle')
  await vi.advanceTimersByTimeAsync(13000)
  expect(wrapper.get('.agent-character .xun-agent').classes()).toContain('wink')
  expect(wrapper.find('.agent-bubble').exists()).toBe(false)
  await vi.advanceTimersByTimeAsync(20000)
  expect(wrapper.get('.agent-character .xun-agent').classes()).toContain('spin')
  expect(wrapper.find('.agent-bubble').exists()).toBe(false)
  await vi.advanceTimersByTimeAsync(15000)
  expect(wrapper.find('.agent-bubble').exists()).toBe(true)
  await wrapper.get('.agent-character').trigger('click')
  expect(wrapper.get('.agent-character .xun-agent').classes()).toContain('idle')
  await vi.advanceTimersByTimeAsync(20000)
  expect(wrapper.get('.agent-character .xun-agent').classes()).toContain('idle')
  wrapper.unmount();vi.useRealTimers()
})


it('starts a new round without silently importing the prior workbench description',async()=>{
 const wrapper=mountAgent()
 await wrapper.setProps({description:'遗失物品：蓝色笔袋。'})
 mocks.api.mockResolvedValue({data:{reply:'记下了',description:'蓝色笔袋',stage:'collecting'}})
 await wrapper.get('.agent-character').trigger('click')
 const say=async(text:string)=>{const field=document.querySelector('textarea')!;field.value=text;field.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()}
 await say('帮我准备寻物启事')
 const reset=[...document.querySelectorAll('button')].find(b=>b.textContent==='新一轮')!
 reset.click();await flushPromises()
 await say('我捡到一副黑色耳机')
 const payload=JSON.parse(mocks.api.mock.calls.filter(x=>x[0]==='/assistant/conversation/').at(-1)![1].body)
 expect(payload.messages).toEqual([{role:'user',content:'我捡到一副黑色耳机'}])
 wrapper.unmount()
})


it('keeps typing and sending available while speech is still being generated',async()=>{
 mocks.api.mockImplementation((path:string,options?:RequestInit)=>{
  if(path==='/assistant/speech/')return new Promise((_resolve,reject)=>options?.signal?.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))))
  return Promise.resolve({data:{reply:'我们继续整理',description:'蓝色耳机',stage:'collecting'}})
 })
 const wrapper=mountAgent();await wrapper.get('.agent-character').trigger('click')
 const voice=[...document.querySelectorAll('button')].find(b=>b.textContent==='开启声音')!;voice.click();await flushPromises()
 const textarea=document.querySelector('textarea')!
 expect(textarea.disabled).toBe(false)
 textarea.value='我丢了蓝色耳机';textarea.dispatchEvent(new Event('input',{bubbles:true}))
 document.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises()
 expect(mocks.api.mock.calls.some(call=>call[0]==='/assistant/conversation/')).toBe(true)
 wrapper.unmount();await flushPromises()
})
