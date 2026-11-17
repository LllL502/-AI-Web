import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import ItemVisual from '../../src/components/ItemVisual.vue'
it('uses the supplied public photograph without a sample label', () => {
  const wrapper = mount(ItemVisual, { props: { title: '校园卡', imageUrl: '/media/public/card.jpg' } })
  expect(wrapper.get('img').attributes('src')).toContain('/media/public/card.jpg')
  expect(wrapper.find('.sample-label').exists()).toBe(false)
})
it('clearly labels category samples when a record has no real photograph', () => {
  const wrapper = mount(ItemVisual, { props: { title: '蓝牙耳机', category: '数码设备', color: '黑色' } })
  expect(wrapper.get('img').attributes('src')).toBe('/local-assets/sample-earbuds.webp')
  expect(wrapper.get('img').attributes('alt')).toContain('并非该物品的实拍照片')
  expect(wrapper.get('.sample-label').text()).toBe('同色类别示意图')
})
it('falls back after a failed public image and resets when it changes', async () => {
  const wrapper = mount(ItemVisual, { props: { title: '校园卡', category: '证件卡片', color: '绿色', imageUrl: '/broken.jpg' } })
  await wrapper.get('img').trigger('error')
  expect(wrapper.get('.sample-label').text()).toBe('同色类别示意图')
  await wrapper.setProps({ imageUrl: '/working.jpg' })
  expect(wrapper.get('img').attributes('src')).toContain('/working.jpg')
  expect(wrapper.find('.sample-label').exists()).toBe(false)
})
it('shows an icon for unrepresented categories and a failed sample', async () => {
  const wrapper = mount(ItemVisual, { props: { title: '笔记本电脑', category: '数码设备', imageUrl: 'javascript:alert(1)' } })
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.text()).toContain('暂无实拍图')
  await wrapper.setProps({ title: '黑色耳机' })
  await wrapper.get('img').trigger('error')
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.text()).toContain('暂无实拍图')
})
