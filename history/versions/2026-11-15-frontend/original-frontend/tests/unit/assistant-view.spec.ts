import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AssistantView from '../../src/views/user/AssistantView.vue'

const mocks = vi.hoisted(() => ({ api: vi.fn() }))

vi.mock('../../src/api/client', async () => {
  const actual = await vi.importActual<typeof import('../../src/api/client')>('../../src/api/client')
  return { ...actual, api: mocks.api }
})

afterEach(() => vi.clearAllMocks())

it('keeps image observations separate until the user corrects and accepts them', async () => {
  mocks.api.mockResolvedValueOnce({ data: {
    provider: { mode: 'openai_compatible', simulated: false, configured: true },
    inputs: { text: true, image: true }, guardrails: [],
  } })
  const wrapper = mount(AssistantView, { global: { stubs: { RouterLink: true } } })
  await flushPromises()
  await wrapper.get('textarea').setValue('我丢了一件物品')
  const file = new File(['image bytes'], 'earbuds.png', { type: 'image/png' })
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
  mocks.api.mockResolvedValueOnce({ data: { observation: '黑色耳机，盒盖有划痕' } })
  const understand = wrapper.findAll('button').find(button => button.text() === '理解图片')!
  await understand.trigger('click')
  await flushPromises()
  expect(mocks.api).toHaveBeenNthCalledWith(2, '/assistant/image/', expect.objectContaining({
    method: 'POST', body: expect.any(FormData),
  }))
  expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('我丢了一件物品')
  await wrapper.get('.follow-ups textarea').setValue('黑色耳机，盒盖没有划痕')
  await wrapper.findAll('button').find(button => button.text() === '确认并加入描述')!.trigger('click')
  expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toContain('黑色耳机，盒盖没有划痕')
  expect(mocks.api).toHaveBeenCalledTimes(2)
})

it('labels the local stub and cites only candidates returned by the real-record endpoint', async () => {
  mocks.api.mockResolvedValueOnce({
    data: {
      provider: { mode: 'development_stub', simulated: true, configured: true },
      inputs: { text: true, image: false },
      guardrails: [],
    },
  })
  const wrapper = mount(AssistantView, {
    global: {
      stubs: {
        RouterLink: { props: ['to'], template: '<a><slot /></a>' },
      },
    },
  })
  await flushPromises()
  expect(wrapper.get('.mode-banner').text()).toContain('不是真实大模型输出')
  expect(wrapper.get('.fallback-link').text()).toContain('普通发布表单')

  mocks.api.mockResolvedValueOnce({
    data: {
      workflow_id: 'workflow-1',
      provider: { name: 'development_stub', model: 'local_rules_v1', simulated: true },
      stages: [
        { id: 'extract', label: '结构化提取', status: 'completed' },
        { id: 'confirm', label: '用户确认', status: 'waiting' },
        { id: 'retrieve', label: '检索真实候选', status: 'blocked' },
      ],
      draft: {
        kind: 'LOST',
        title: '寻找黑色耳机',
        category_hint: '耳机',
        brand: 'Sony',
        colors: ['黑色'],
        occurred_at: null,
        location_hint: '图书馆',
        public_description: '图书馆丢了黑色 Sony 耳机',
        uncertain_fields: ['occurred_at'],
        source_spans: { title: '黑色耳机' },
      },
      follow_up_questions: [
        { field: 'occurred_at', question: '大约什么时间？', reason: '排除时间冲突。', required: false },
      ],
    },
  })
  await wrapper.get('textarea').setValue('图书馆丢了黑色 Sony 耳机')
  await wrapper.get('.input-panel form').trigger('submit')
  await flushPromises()

  expect(wrapper.get('.confirmation-panel').text()).toContain('确认物品信息')
  expect(wrapper.get('.workflow-panel').text()).toContain('等待你确认')
  expect(mocks.api).toHaveBeenNthCalledWith(2, '/assistant/prepare/', expect.objectContaining({ method: 'POST' }))

  mocks.api.mockResolvedValueOnce({
    data: {
      retrieval_method: 'public_keyword_retrieval_v1',
      semantic_retrieval: false,
      message: '已取回真实候选。',
      candidates: [{
        id: 'item-1',
        citation_id: 'item:item-1',
        title: '图书馆拾到黑色耳机',
        description: '公开描述',
        category: '耳机',
        brand: 'Sony',
        color: '黑色',
        occurred_at: '2026-11-13T10:00:00+08:00',
        location: '图书馆',
        image_url: '',
        url: '/items/item-1',
        reasons: ['公开描述命中：黑色、耳机'],
      }],
      stations: [],
      stages: [
        { id: 'extract', label: '结构化提取', status: 'completed' },
        { id: 'confirm', label: '用户确认', status: 'completed' },
        { id: 'retrieve', label: '检索真实候选', status: 'completed' },
        { id: 'explain', label: '证据解释', status: 'completed' },
      ],
    },
  })
  const searchButton = wrapper.findAll('button').find((button) => button.text().includes('检索真实公开候选'))
  expect(searchButton).toBeTruthy()
  await searchButton!.trigger('click')
  await flushPromises()

  expect(wrapper.get('.candidate-card').text()).toContain('item:item-1')
  expect(wrapper.get('.results-section').text()).toContain('语义和图片召回尚未启用')
  expect(mocks.api).toHaveBeenNthCalledWith(3, '/assistant/search/', expect.objectContaining({ method: 'POST' }))
})

