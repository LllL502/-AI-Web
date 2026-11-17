import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AppIcon from '../../src/components/AppIcon.vue'

describe('AppIcon', () => {
  it('renders one decorative SVG path for the requested icon', () => {
    const wrapper = mount(AppIcon, { props: { name: 'shield' } })
    expect(wrapper.find('svg').attributes('aria-hidden')).toBe('true')
    expect(wrapper.findAll('path')).toHaveLength(1)
    expect(wrapper.find('path').attributes('d')).toContain('12 2')
  })

  it('uses the box path only for the box icon', () => {
    const wrapper = mount(AppIcon, { props: { name: 'box' } })
    expect(wrapper.find('path').attributes('d')).toContain('8-4')
  })
})
