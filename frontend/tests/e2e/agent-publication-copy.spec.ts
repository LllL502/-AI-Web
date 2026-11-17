import {expect,test} from '@playwright/test'
import fs from 'node:fs/promises'
async function login(page:import('@playwright/test').Page){
 await page.goto('/login?redirect=/home')
 await page.getByLabel('用户名',{exact:true}).fill('student_01')
 await page.getByLabel('密码',{exact:true}).fill('CampusTrace!2026')
 await page.getByRole('button',{name:'登录',exact:true}).click()
 await page.locator('.agent-character').click()
}
test('conflicting lost and found statements ask for clarification before a draft',async({page})=>{
 await login(page)
 await page.getByLabel('告诉小寻你记得的情况').fill('我昨天晚上10点在田径场捡到了一副黑色耳机。补充：我的黑色耳机不见了。')
 await page.getByRole('button',{name:'发送 ↑'}).click()
 await expect(page.getByText('你提到了“捡到”和“丢失”。这次是你捡到了别人的物品，还是你自己的物品丢了？',{exact:true})).toBeVisible()
 await expect(page.getByRole('button',{name:/帮我发布/})).toHaveCount(0)
 if(process.env.CAMPUSTRACE_REAL_LOCAL_AI==='1'){
  const resolved=page.waitForResponse(r=>r.url().endsWith('/assistant/conversation/')&&r.request().method()==='POST',{timeout:90_000})
  await page.getByLabel('告诉小寻你记得的情况').fill('我自己的耳机丢了')
  await page.getByRole('button',{name:'发送 ↑'}).click()
  const response=await resolved;expect(response.status()).toBe(200)
  const body=await response.json();expect(body.data.publication.kind).toBe('LOST')
  expect(body.data.publication.description).toContain('田径场')
  expect(body.data.publication.title).toContain('黑色耳机')
 }
})
test('real local model extracts a concise editable publication without virtual photos',async({page})=>{
 test.skip(process.env.CAMPUSTRACE_REAL_LOCAL_AI!=='1','Requires local models')
 test.setTimeout(180_000)
 await login(page)
 const source='昨天晚上10点多，我在田径场捡到一副黑色耳机，充电盒盖有一道浅划痕，没有挂件。帮我发条招领吧，我有点赶时间。'
 await page.getByLabel('告诉小寻你记得的情况').fill(source)
 const response=page.waitForResponse(r=>r.url().endsWith('/assistant/conversation/')&&r.request().method()==='POST',{timeout:100_000})
 await page.getByRole('button',{name:'发送 ↑'}).click()
 const result=await response;expect(result.status()).toBe(200)
 const body=await result.json();const pub=body.data.publication
 expect(pub.kind).toBe('FOUND')
 expect(pub.title).toContain('黑色耳机');expect(pub.title.length).toBeLessThan(30)
 expect(pub.description).toContain('浅划痕');expect(pub.description).toContain('没有挂件')
 expect(pub.description).toContain('田径场');expect(pub.description).not.toMatch(/帮我|赶时间|补充[:：]|已填的物品描述/)
 expect(pub.description).not.toBe(source)
 await fs.writeFile('../artifacts/agent-publication-copy.json',JSON.stringify({input:source,publication:pub,extraction_provider:body.data.extraction_provider},null,2))
 await page.getByRole('button',{name:'帮我发布招领信息'}).click()
 await expect(page.getByLabel('标题',{exact:true})).toHaveValue(pub.title)
 await expect(page.getByLabel('物品描述',{exact:true})).toHaveValue(pub.description)
 await page.getByLabel('标题',{exact:true}).fill('田径场拾到黑色耳机')
 await page.screenshot({path:'../artifacts/agent-publication-copy-preview.png',fullPage:true})
 await page.getByRole('button',{name:'暂不提交'}).click()
 await page.getByRole('button',{name:'关闭聊天'}).click()
 const old=page.getByRole('link').filter({hasText:'已填的物品描述'}).first()
 if(await old.count()){
  await old.click();await expect(page.locator('.item-photo--detail img')).toHaveCount(0)
  await expect(page.locator('.item-photo--detail')).toContainText('暂无实拍图')
  await page.screenshot({path:'../artifacts/agent-publication-no-fake-photo.png',fullPage:true})
 }
})
