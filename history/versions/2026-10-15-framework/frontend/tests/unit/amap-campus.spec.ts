import { mount, flushPromises } from '@vue/test-utils'
import { it, expect, vi, beforeEach } from 'vitest'
import AMapCampus from '../../src/components/AMapCampus.vue'
const mocks=vi.hoisted(()=>({api:vi.fn(),load:vi.fn()}))
vi.mock('../../src/api/client',()=>({api:mocks.api}))
vi.mock('../../src/api/amap',()=>({loadAMap:mocks.load}))
beforeEach(()=>vi.clearAllMocks())

it('searches school only for an unverified placeholder and displays the warning',async()=>{
  const search=vi.fn((_query:string,callback:Function)=>callback('complete',{poiList:{pois:[]}}))
  class Map {destroy=vi.fn();addControl=vi.fn();setZoomAndCenter=vi.fn();on=vi.fn()}
  class PlaceSearch {search=search}
  mocks.api.mockResolvedValue({data:{enabled:true,web_key:'key',service_host:'/_AMapService',campus:{school:'成都医学院',name:'主校区',city:'成都市',verified:false,is_demo:false}}})
  mocks.load.mockResolvedValue({Map,PlaceSearch,Scale:class{},ToolBar:class{}})
  const wrapper=mount(AMapCampus)
  await flushPromises()
  expect(search.mock.calls[0][0]).toBe('成都医学院')
  expect(wrapper.text()).not.toContain('校区资料待核实')
  wrapper.unmount()
})
it('shows a useful fallback without requesting SDK when credentials are absent',async()=>{
  mocks.api.mockResolvedValue({data:{enabled:false,notice:'地图服务暂不可用，仍可使用地点列表'}})
  const wrapper=mount(AMapCampus)
  await flushPromises()
  expect(wrapper.text()).toContain('地图服务暂不可用')
  expect(mocks.load).not.toHaveBeenCalled()
  wrapper.unmount()
})
it('uses the virtual campus map for demo data and emits only a protected location',async()=>{
  mocks.api.mockImplementation((path:string)=>Promise.resolve(path==='/maps/config/'
    ? {data:{enabled:false,notice:'演示校区使用虚拟布局',campus:{school:'演示学校',name:'演示校区',city:'',verified:true,is_demo:true}}}
    : {data:{locations:[{id:2,name:'逸夫图书馆',code:'zone-01',count:3,stations:[]}]}}))
  const wrapper=mount(AMapCampus,{props:{pickable:true,selectedPreciseLocation:'逸夫图书馆'}})
  await flushPromises()

  expect(wrapper.text()).toContain('演示校区 · 虚拟布局')
  expect(wrapper.text()).toContain('逸夫图书馆')
  expect(mocks.load).not.toHaveBeenCalled()
  await wrapper.get('button.map-node').trigger('click')
  expect(wrapper.emitted('select-protected-location')?.[0]?.[0]).toMatchObject({id:2,name:'逸夫图书馆'})
  wrapper.unmount()
})
it('destroys the provider map when leaving the page',async()=>{
  const destroy=vi.fn()
  class Map {destroy=destroy;addControl=vi.fn();setZoomAndCenter=vi.fn();on=vi.fn()}
  class PlaceSearch {search(_query:string,callback:Function){callback('complete',{poiList:{pois:[]}})}}
  mocks.api.mockResolvedValue({data:{enabled:true,web_key:'key',service_host:'/_AMapService',campus:{school:'学校',name:'校区',city:'西安市',verified:true,is_demo:false}}})
  mocks.load.mockResolvedValue({Map,PlaceSearch,Scale:class{},ToolBar:class{}})
  const wrapper=mount(AMapCampus)
  await flushPromises()
  expect(wrapper.text()).toContain('没有找到地点')
  wrapper.unmount()
  expect(destroy).toHaveBeenCalledOnce()
})

it('never exposes submit controls when embedded in a publish form',async()=>{
  const search=vi.fn((_query:string,callback:Function)=>callback('complete',{poiList:{pois:[{id:'poi-1',name:'图书馆',address:'校园东区',location:{getLat:()=>34.2,getLng:()=>108.9}}]}}))
  class Map {destroy=vi.fn();addControl=vi.fn();setZoomAndCenter=vi.fn();on=vi.fn();remove=vi.fn();add=vi.fn()}
  class PlaceSearch {search=search}
  mocks.api.mockResolvedValue({data:{enabled:true,web_key:'key',service_host:'/_AMapService',campus:{school:'学校',name:'校区',city:'西安市',verified:true,is_demo:false}}})
  mocks.load.mockResolvedValue({Map,PlaceSearch,Marker:class{},Scale:class{},ToolBar:class{}})
  const wrapper=mount(AMapCampus,{props:{pickable:true}})
  await flushPromises()

  expect(wrapper.find('form').exists()).toBe(false)
  expect(wrapper.findAll('button').length).toBeGreaterThan(0)
  expect(wrapper.findAll('button').every((button)=>button.attributes('type')==='button')).toBe(true)
  await wrapper.get('.poi-results button').trigger('click')
  expect(wrapper.emitted('select-map-place')?.[0]?.[0]).toMatchObject({
    name:'图书馆',address:'校园东区',latitude:34.2,longitude:108.9,
  })
  wrapper.unmount()
})
