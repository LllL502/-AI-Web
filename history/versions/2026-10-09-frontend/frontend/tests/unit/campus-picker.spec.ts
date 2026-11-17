import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import CampusPicker from '../../src/components/CampusPicker.vue'
import { createPinia, setActivePinia } from 'pinia'
const mockApi = vi.hoisted(() => vi.fn())
vi.mock('../../src/api/client', () => ({ api: mockApi }))
const school = { id:1, name:'西安交通大学', province:'陕西省', city:'西安市', is_demo:false, campuses:[{id:2,name:'兴庆校区'},{id:3,name:'曲江校区'}] }
beforeEach(() => { setActivePinia(createPinia()); localStorage.clear(); document.body.innerHTML=''; mockApi.mockReset() })
it('opens a school panel and lists only the chosen school campuses', async () => {
  mockApi.mockResolvedValue({data:{schools:[school],total:1,page:1,pages:1}})
  const wrapper = mount(CampusPicker, { attachTo:document.body })
  await flushPromises()
  await wrapper.find('button').trigger('click'); await flushPromises()
  const result=document.querySelector('.school-results button') as HTMLButtonElement
  result.click(); await flushPromises()
  expect(document.querySelectorAll('.campus-results option')).toHaveLength(3)
  expect((document.querySelector('footer button') as HTMLButtonElement).disabled).toBe(true)
  expect(document.querySelector('.campus-results')?.textContent).toContain('曲江校区')
  wrapper.unmount()
})
it('does not allow switching to a school without verified campuses', async () => {
  mockApi.mockResolvedValue({data:{schools:[{...school,campuses:[]}],total:1,page:1,pages:1}})
  const wrapper=mount(CampusPicker,{attachTo:document.body})
  await flushPromises(); await wrapper.find('button').trigger('click'); await flushPromises()
  ;(document.querySelector('.school-results button') as HTMLButtonElement).click(); await flushPromises()
  expect(document.body.textContent).toContain('校区资料待核实')
  expect((document.querySelector('footer button') as HTMLButtonElement).disabled).toBe(true)
  wrapper.unmount()
})
