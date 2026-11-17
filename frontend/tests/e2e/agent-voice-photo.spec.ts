import { expect, test } from '@playwright/test'
import path from 'node:path'

async function login(page:import('@playwright/test').Page){
  await page.goto('/login?redirect=/home')
  await page.getByLabel('用户名',{exact:true}).fill('student_01')
  await page.getByLabel('密码',{exact:true}).fill('CampusTrace!2026')
  await page.getByRole('button',{name:'登录',exact:true}).click()
  await page.locator('.agent-character').click()
}

test('local neural child voice plays on request and stops when chat closes',async({page})=>{
  test.skip(process.env.CAMPUSTRACE_REAL_VOICE!=='1','Requires installed local neural voice')
  test.setTimeout(180_000)
  await page.addInitScript(()=>{
    ;(window as any).__xunAudioEvents=[]
    window.Audio=new Proxy(window.Audio,{construct(target,args){
      const audio=Reflect.construct(target,args) as HTMLAudioElement
      ;(window as any).__xunAudio=audio
      audio.addEventListener('playing',()=>{(window as any).__xunAudioEvents.push('playing')})
      return audio
    }})
  })
  await login(page)
  expect(await page.evaluate(()=>(window as any).__xunAudioEvents)).toHaveLength(0)
  await page.route('**/assistant/conversation/',route=>route.fulfill({json:{data:{stage:'collecting',description:'',reply:'记不清也没关系呀。想一想，最后一次见到它，是在什么地方呢？'}}}))
  await page.getByLabel('告诉小寻你记得的情况').fill('我的耳机不见了。')
  await page.getByRole('button',{name:'发送 ↑'}).click()
  await expect(page.getByText('记不清也没关系呀。想一想，最后一次见到它，是在什么地方呢？',{exact:true})).toBeVisible()
  const response=page.waitForResponse(r=>r.url().endsWith('/assistant/speech/')&&r.request().method()==='POST',{timeout:120_000})
  await page.getByRole('button',{name:'开启声音'}).click()
  const generated=await response
  expect(generated.status()).toBe(200)
  const data=await generated.json()
  expect(data.data.voice).toBe('xun-child-v1')
  expect(Buffer.from(data.data.audio,'base64').subarray(0,4).toString()).toBe('RIFF')
  await expect.poll(()=>page.evaluate(()=>(window as any).__xunAudioEvents.length)).toBe(1)
  await expect(page.locator('.chat-mini-agent .xun-agent')).toHaveClass(/speaking/)
  await page.screenshot({path:'../artifacts/xun-neural-voice-playing.png',fullPage:true})
  await page.getByRole('button',{name:'关闭聊天'}).click()
  await expect(page.locator('.agent-character .xun-agent')).not.toHaveClass(/speaking/)
  expect(await page.evaluate(()=>(window as any).__xunAudio.paused)).toBe(true)
})

test('real photo can be understood and searched entirely inside the agent chat',async({page})=>{
  test.skip(process.env.CAMPUSTRACE_REAL_LOCAL_AI!=='1','Requires local models')
  test.setTimeout(180_000)
  await login(page)
  await page.locator('.xun-chat-compose input[type=file]').setInputFiles(path.resolve('../data/demo-images/black-earbuds.png'))
  await expect(page.locator('.chat-photo-review textarea')).toHaveValue(/耳机/,{timeout:90_000})
  await page.getByRole('button',{name:'外观正确，帮我查找'}).click()
  await expect(page.locator('.agent-tool-status')).toContainText('已检索真实线索',{timeout:90_000})
  await expect(page.locator('.agent-candidate').first()).toBeVisible()
  await expect(page).toHaveURL(/\/home$/)
  await page.screenshot({path:'../artifacts/xun-agent-photo-audit.png',fullPage:true})
})
