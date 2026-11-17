import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PublishView from '../../src/views/user/PublishView.vue'

const mocks = vi.hoisted(() => ({
  api: vi.fn(),
  push: vi.fn(),
}))

vi.mock('../../src/api/client', () => ({
  api: mocks.api,
  readableApiError: (_reason: unknown, fallback: string) => fallback,
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.push }),
}))

const completeDraft = {
  title: '一串三把的钥匙',
  category: '10',
  description: '银色钥匙串，含三把钥匙。',
  brand: '',
  color: '银色',
  occurred_at: '2026-10-11T18:30',
  location: '25',
  location_detail: '',
  location_candidate_ids: [],
  location_candidate_points: [],
  station: '',
}

function metadata(locationId = 25) {
  return {
    data: {
      campus: { id: 2, name: '兴庆校区', school: '西安交通大学', is_demo: false },
      categories: [{ id: 10, name: '钥匙', parent_id: 1 }],
      locations: [{ id: locationId, name: locationId === 25 ? '兴庆校区' : '雁塔校区', parent_id: null }],
      stations: [],
    },
  }
}

function mountView(amapStub: unknown = true) {
  return mount(PublishView, {
    props: { kind: 'LOST' },
    global: {
      stubs: {
        AppIcon: true,
        AMapCampus: amapStub,
      },
    },
  })
}

describe('PublishView campus-safe draft handling', () => {
  beforeEach(() => {
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:photo-preview') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    localStorage.setItem('campustrace-campus', '2')
    localStorage.setItem('campustrace-draft-2-lost', JSON.stringify(completeDraft))
  })

  afterEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('shows the public location name instead of its database id on confirmation', async () => {
    mocks.api.mockResolvedValueOnce(metadata())
    const wrapper = mountView()
    await flushPromises()

    await wrapper.findAll('.stepper button')[2].trigger('click')

    const review = wrapper.get('.review-card').text()
    expect(review).toContain('公开地点兴庆校区')
    expect(review).not.toContain('公开地点25')
  })

  it('offers only the selected campus as the public location', async () => {
    const response = metadata()
    response.data.locations.push({ id: 99, name: '逸夫图书馆', parent_id: 25 })
    mocks.api.mockResolvedValueOnce(response)
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('.stepper button')[1].trigger('click')

    const publicLocation = wrapper.get('select[required]')
    expect(publicLocation.findAll('option')).toHaveLength(1)
    expect(publicLocation.text()).toContain('兴庆校区')
    expect(publicLocation.text()).not.toContain('逸夫图书馆')
    expect(publicLocation.attributes('disabled')).toBeDefined()
  })

  it('records ranked possible locations without changing the public campus', async () => {
    const response = metadata()
    response.data.locations.push({ id: 99, name: '逸夫图书馆', parent_id: 25 })
    mocks.api.mockResolvedValueOnce(response)
    const wrapper = mountView({
      template: '<button class="demo-location" type="button" @click="$emit(\'select-protected-location\',{id:99,name:\'逸夫图书馆\'})">逸夫图书馆</button>',
    })
    await flushPromises()
    await wrapper.findAll('.stepper button')[1].trigger('click')
    await wrapper.get('.demo-location').trigger('click')

    expect(wrapper.get('.location-ranking').text()).toContain('最可能逸夫图书馆')
    expect((wrapper.get('select[required]').element as HTMLSelectElement).value).toBe('25')
  })

  it('keeps multiple ranked candidates selected from a real campus map', async () => {
    mocks.api.mockResolvedValueOnce(metadata())
    const wrapper = mountView({
      template: `<div>
        <button class="real-point-one" type="button" @click="$emit('pick',{latitude:34.246007,longitude:108.981431,label:'工程坊'})">工程坊</button>
        <button class="real-point-two" type="button" @click="$emit('pick',{latitude:34.2471,longitude:108.9843,label:'钱学森图书馆'})">图书馆</button>
      </div>`,
    })
    await flushPromises()
    await wrapper.findAll('.stepper button')[1].trigger('click')
    await wrapper.get('.real-point-one').trigger('click')
    await wrapper.get('.real-point-two').trigger('click')

    const ranking = wrapper.get('.location-ranking').text()
    expect(ranking).toContain('最可能工程坊')
    expect(ranking).toContain('可能 2钱学森图书馆')
    expect(wrapper.text()).toContain('已选择 2 个地图候选点')
  })

  it('clears a stale location id when the current campus dictionary no longer contains it', async () => {
    mocks.api.mockResolvedValueOnce(metadata(26))
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('.form-message.warning').text()).toContain('旧草稿中的公开地点已失效')
    await wrapper.findAll('.stepper button')[1].trigger('click')
    expect((wrapper.get('select[required]').element as HTMLSelectElement).value).not.toBe('25')
  })

  it('continues from item creation to the submit-for-review endpoint', async () => {
    mocks.api
      .mockResolvedValueOnce(metadata())
      .mockResolvedValueOnce({ data: { id: 'item-1' } })
      .mockResolvedValueOnce({ data: { id: 'item-1', review_status: 'PENDING' } })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('.stepper button')[2].trigger('click')
    await wrapper.get('input[type="checkbox"]').setValue(true)

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mocks.api).toHaveBeenNthCalledWith(2, '/items/', expect.objectContaining({ method: 'POST' }))
    expect(mocks.api).toHaveBeenNthCalledWith(3, '/items/item-1/submit/', { method: 'POST' })
    expect(wrapper.text()).toContain('已提交审核')
  })

  it('does not create an item when the form is submitted from the location step', async () => {
    mocks.api.mockResolvedValueOnce(metadata())
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('.stepper button')[1].trigger('click')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mocks.api).toHaveBeenCalledTimes(1)
    expect(wrapper.get('.form-message.error').text()).toContain('点击“下一步”完成确认')
  })

  it('uploads selected photos before submitting and saves their display order', async () => {
    mocks.api
      .mockResolvedValueOnce(metadata())
      .mockResolvedValueOnce({ data: { id: 'item-photo' } })
      .mockResolvedValueOnce({ data: { created: [{ id: 7, file: '/media/key.webp', sort_order: 0 }], media: [] } })
      .mockResolvedValueOnce({ data: { media: [{ id: 7, file: '/media/key.webp', sort_order: 0 }] } })
      .mockResolvedValueOnce({ data: { id: 'item-photo', review_status: 'PENDING' } })
    const wrapper = mountView()
    await flushPromises()

    const input = wrapper.get('input[type="file"]')
    const file = new File(['jpeg-content'], 'keys.jpg', { type: 'image/jpeg' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await flushPromises()
    expect(wrapper.findAll('.photo-card')).toHaveLength(1)

    await wrapper.findAll('.stepper button')[2].trigger('click')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mocks.api).toHaveBeenNthCalledWith(3, '/items/item-photo/media/', expect.objectContaining({
      method: 'POST',
      body: expect.any(FormData),
    }))
    expect(mocks.api).toHaveBeenNthCalledWith(4, '/items/item-photo/media-order/', expect.objectContaining({ method: 'PATCH' }))
    expect(mocks.api).toHaveBeenNthCalledWith(5, '/items/item-photo/submit/', { method: 'POST' })
  })
})
