import { expect,it } from 'vitest'
import { xunSpokenText } from '../../src/utils/xunVoice'
it('speaks short natural turns instead of reading a long result card',()=>{
 expect(xunSpokenText('别着急，咱们一起找！你记得它是什么颜色吗？')).toContain('别着急')
 expect(xunSpokenText('很长的回复。'.repeat(50)).length).toBeLessThanOrEqual(80)
 expect(xunSpokenText('看这里 https://example.com 移步查看。')).not.toContain('https')
})
