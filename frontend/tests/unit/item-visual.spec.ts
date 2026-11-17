import { mount } from '@vue/test-utils'
import { expect,it } from 'vitest'
import ItemVisual from '../../src/components/ItemVisual.vue'
it('uses only the supplied photograph',()=>{
 const w=mount(ItemVisual,{props:{title:'校园卡',imageUrl:'/media/public/card.jpg'}})
 expect(w.get('img').attributes('src')).toContain('/media/public/card.jpg')
})
it.each(['黑色耳机','蓝色水杯','绿色校园卡'])('never supplies a virtual photo for %s',title=>{
 const w=mount(ItemVisual,{props:{title}})
 expect(w.find('img').exists()).toBe(false)
 expect(w.text()).toContain('暂无实拍图')
})
it('failed and unsafe images stay as placeholders, and a replacement real photo works',async()=>{
 const w=mount(ItemVisual,{props:{title:'黑色耳机',imageUrl:'/broken.jpg'}})
 await w.get('img').trigger('error')
 expect(w.find('img').exists()).toBe(false)
 await w.setProps({imageUrl:'javascript:alert(1)'})
 expect(w.find('img').exists()).toBe(false)
 await w.setProps({imageUrl:'/working.jpg'})
 expect(w.get('img').attributes('src')).toContain('/working.jpg')
})
