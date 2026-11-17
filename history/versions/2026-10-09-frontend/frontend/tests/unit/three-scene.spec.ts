import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeAll, describe, expect, it, vi } from 'vitest'

beforeAll(() => {
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
  })
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  })
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
})

describe('ThreeScene fallback', () => {
  it('keeps match evidence operable when WebGL is unavailable', async () => {
    const { default: ThreeScene } = await import('../../src/components/ThreeScene.vue')
    const wrapper = mount(ThreeScene, {
      props: {
        mode: 'match',
        label: '真实匹配关系',
        fallbackItems: ['候选甲 · 88.0 分'],
        matchSourceLabel: '我的遗失：校园卡',
        matchCandidates: [{ label: '候选甲 · 88.0 分', score: 0.88 }],
      },
    })
    await nextTick()
    expect(wrapper.get('[role="region"]').attributes('aria-label')).toContain('二维回退')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual(['候选甲 · 88.0 分'])
    wrapper.unmount()
  })
})
