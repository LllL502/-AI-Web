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
  expect(wrapper.text()).toContain('校区资料待核实')
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
