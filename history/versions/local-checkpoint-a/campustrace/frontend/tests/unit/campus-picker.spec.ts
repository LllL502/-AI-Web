import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import CampusPicker from '../../src/components/CampusPicker.vue'
import { createPinia, setActivePinia } from 'pinia'
const mockApi = vi.hoisted(() => vi.fn())
vi.mock('../../src/api/amap',()=>({loadAMap:async()=>({PlaceSearch:class{setPageIndex(){} search(_q:string,callback:Function){callback('complete',{poiList:{pois:[]}})}}})}))
vi.mock('../../src/api/client', () => ({ api: mockApi }))
vi.mock('vue-router',()=>({useRouter:()=>({replace:vi.fn().mockResolvedValue(undefined)})}))
const school = { id:1, name:'西安交通大学', province:'陕西省', city:'西安市', is_demo:false, campuses:[{id:2,name:'兴庆校区'},{id:3,name:'曲江校区'}] }
beforeEach(() => { setActivePinia(createPinia()); localStorage.clear(); document.body.innerHTML=''; mockApi.mockReset() })
it('shows the last selected campus immediately while the directory refreshes',()=>{
  localStorage.setItem('campustrace-campus-label','西安交通大学 · 兴庆校区')
  mockApi.mockReturnValue(new Promise(()=>undefined))
  const wrapper=mount(CampusPicker)
  expect(wrapper.get('.campus-trigger').text()).toContain('西安交通大学 · 兴庆校区')
  wrapper.unmount()
})
it('allows manual refresh for a verified school without automatically searching',async()=>{
  const verified={...school,campuses:school.campuses.map(c=>({...c,verification_status:'VERIFIED'}))}
  const internalCandidate={id:99,name:'重复地图候选校区',verification_status:'UNVERIFIED',source_url:'https://www.amap.com/detail/POI99'}
  mockApi.mockImplementation((path:string)=>Promise.resolve(path==='/maps/config/'?{data:{web_key:'key',service_host:'/_AMapService'}}:path.includes('discover-campuses')?{data:{campuses:[...verified.campuses,internalCandidate],notice:''}}:{data:{schools:[verified],total:1,page:1,pages:1}}))
  const wrapper=mount(CampusPicker,{attachTo:document.body})
  await flushPromises();await wrapper.find('button').trigger('click');await flushPromises()
  ;(document.querySelector('.school-results button') as HTMLButtonElement).click();await flushPromises()
  expect(mockApi.mock.calls.some(([path])=>path==='/maps/discover-campuses/')).toBe(false)
  const refresh=Array.from(document.querySelectorAll('.campus-results button')).find(b=>b.textContent==='刷新校区') as HTMLButtonElement
  expect(refresh).toBeTruthy();refresh.click();await flushPromises()
  const call=mockApi.mock.calls.find(([path])=>path==='/maps/discover-campuses/')!
  expect(JSON.parse(call[1].body)).toEqual({school:1,refresh:true})
  expect(document.querySelector('.campus-results select')?.textContent).toContain('兴庆校区')
  expect(document.querySelector('.campus-results select')?.textContent).not.toContain('重复地图候选校区')
  wrapper.unmount()
})
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
  mockApi.mockImplementation((path:string)=>path==='/maps/config/'?Promise.resolve({data:{web_key:'test-key',service_host:'/_AMapService'}}):path.includes('discover-campuses')?Promise.resolve({data:{campuses:[],notice:'未找到校区'}}):Promise.resolve({data:{schools:[{...school,campuses:[]}],total:1,page:1,pages:1}}))
  const wrapper=mount(CampusPicker,{attachTo:document.body})
  await flushPromises(); await wrapper.find('button').trigger('click'); await flushPromises()
  ;(document.querySelector('.school-results button') as HTMLButtonElement).click(); await flushPromises()
  expect(document.body.textContent).toContain('暂无可选校区')
  expect((document.querySelector('footer button') as HTMLButtonElement).disabled).toBe(true)
  wrapper.unmount()
})

it('adds discovered map campuses to the top selector instead of only showing a placeholder',async()=>{
  const placeholder={id:9,name:'主校区',verification_status:'UNVERIFIED'}
  mockApi.mockImplementation((path:string)=>Promise.resolve(path==='/maps/config/'?{data:{web_key:'test-key',service_host:'/_AMapService'}}:path.includes('discover-campuses')?{data:{campuses:[placeholder,{id:10,name:'新都校区',verification_status:'UNVERIFIED',source_url:'https://www.amap.com/detail/POI1'},{id:11,name:'天回校区',verification_status:'UNVERIFIED',source_url:'https://www.amap.com/detail/POI2'}],notice:'候选待确认'}}:{data:{schools:[{...school,campuses:[placeholder]}],total:1,page:1,pages:1}}))
  const wrapper=mount(CampusPicker,{attachTo:document.body})
  await flushPromises();await wrapper.find('button').trigger('click');await flushPromises()
  ;(document.querySelector('.school-results button') as HTMLButtonElement).click();await flushPromises()
  expect(document.querySelector('.campus-results select')?.textContent).toContain('新都校区')
  expect(document.querySelector('.campus-results select')?.textContent).not.toContain('主校区')
  expect(document.body.textContent).not.toMatch(/资料待核实|待确认|仍需核实/)
  expect(mockApi.mock.calls.some(([path])=>path==='/maps/discover-campuses/')).toBe(true)
  wrapper.unmount()
})

it('keeps only the main campus when discovery yields a single map campus',async()=>{
  const entries=[{id:9,name:'主校区',verification_status:'UNVERIFIED'},{id:10,name:'新都校区',verification_status:'UNVERIFIED',source_url:'https://www.amap.com/detail/POI1'}]
  mockApi.mockImplementation((path:string)=>Promise.resolve(path==='/maps/config/'?{data:{web_key:'test-key',service_host:'/_AMapService'}}:path.includes('discover-campuses')?{data:{campuses:entries,notice:''}}:{data:{schools:[{...school,campuses:entries}],total:1,page:1,pages:1}}))
  const wrapper=mount(CampusPicker,{attachTo:document.body})
  await flushPromises();await wrapper.find('button').trigger('click');await flushPromises()
  ;(document.querySelector('.school-results button') as HTMLButtonElement).click();await flushPromises()
  expect(document.querySelector('.campus-results select')?.textContent).toContain('主校区')
  expect(document.querySelector('.campus-results select')?.textContent).not.toContain('新都校区')
  wrapper.unmount()
})
