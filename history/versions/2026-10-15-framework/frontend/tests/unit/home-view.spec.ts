import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, expect, it, vi } from 'vitest'
import HomeView from '../../src/views/public/HomeView.vue'
const mocks = vi.hoisted(() => ({ api: vi.fn(), push: vi.fn() }))
vi.mock('../../src/api/client', () => ({ apiCached: mocks.api, ApiError: class extends Error {} }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push }), RouterLink: { props: ['to'], template: '<a><slot /></a>' } }))
const mountHome = () => mount(HomeView, { global: { stubs: { AMapCampus: true } } })
const item = { id: '1', title: '校园卡', category_name: '证件卡片', location_name: '图书馆', occurred_at: '2026-10-09', description: '请核对物品特征' }
beforeEach(() => vi.resetAllMocks())
it('shows public items and passes the search to the correct gallery', async () => {
  mocks.api.mockImplementation((path: string) => path.includes('metadata')
    ? Promise.resolve({ data: { categories: [] } })
    : Promise.resolve({ data: { items: [item] } }))
  const wrapper = mountHome(); await flushPromises()
  expect(wrapper.find('.latest-card').text()).toContain('校园卡')
  await wrapper.find('input').setValue('黑色耳机')
  await wrapper.find('form').trigger('submit')
  expect(mocks.push).toHaveBeenCalledWith({ path: '/found', query: { q: '黑色耳机' } })
})
it('ignores an old response after switching between found and lost items', async () => {
  let resolveOld!: (value: unknown) => void
  let itemRequests = 0
  mocks.api.mockImplementation((path: string) => {
    if (path.includes('metadata')) return Promise.resolve({ data: { categories: [] } })
    itemRequests += 1
    if (itemRequests === 1) return new Promise(resolve => { resolveOld = resolve })
    return Promise.resolve({ data: { items: [{ ...item, title: '寻找钥匙' }] } })
  })
  const wrapper = mountHome()
  await wrapper.findAll('.kind-switch button')[1]!.trigger('click'); await flushPromises()
  resolveOld({ data: { items: [item] } }); await flushPromises()
  expect(wrapper.find('.latest-card').text()).toContain('寻找钥匙')
})
it('shows a retry after a failed request and an honest empty state', async () => {
  let itemRequests = 0
  mocks.api.mockImplementation((path: string) => {
    if (path.includes('metadata')) return Promise.resolve({ data: { categories: [] } })
    itemRequests += 1
    return itemRequests === 1 ? Promise.reject(new Error('offline')) : Promise.resolve({ data: { items: [] } })
  })
  const wrapper = mountHome(); await flushPromises()
  expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  await wrapper.find('[role="alert"] button').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('暂时没有公开物品')
  expect(wrapper.find('.latest-card').exists()).toBe(false)
})
