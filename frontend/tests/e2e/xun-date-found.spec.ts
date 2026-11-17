import {expect,test} from '@playwright/test'
import fs from 'node:fs/promises'
test('real conversation separates yesterday from place and completes found publication through chat',async({page})=>{
 test.skip(process.env.CAMPUSTRACE_REAL_LOCAL_AI!=='1','Requires local models')
 test.setTimeout(300_000)
 await page.goto('/login?redirect=/home')
 await page.getByLabel('用户名',{exact:true}).fill('student_01');await page.getByLabel('密码',{exact:true}).fill('CampusTrace!2026')
 await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('.agent-character').click()
 const audit:any[]=[];let writes=0
 async function say(text:string){
  const response=page.waitForResponse(r=>r.url().endsWith('/assistant/conversation/')&&r.request().method()==='POST',{timeout:110_000})
  await page.getByLabel('告诉小寻你记得的情况').fill(text);await page.getByRole('button',{name:'发送 ↑'}).click()
  const r=await response;const body=await r.json();expect(r.status(),JSON.stringify(body)).toBe(200)
  audit.push({user:text,...body.data});await fs.writeFile('../artifacts/xun-date-found-audit.json',JSON.stringify(audit,null,2))
  await expect(page.locator('.chat-thinking')).toHaveCount(0);return body.data
 }
 const lost=await say('我昨天晚上丢了一个蓝色笔袋，不知道在哪里丢的，帮我准备一条寻物启事')
 expect(lost.draft.location_hint).not.toMatch(/昨天|晚上/)
 expect(lost.publication.occurred_date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
 await expect(page.locator('.agent-publication')).toBeVisible()
 await expect(page.getByLabel('事件日期',{exact:true})).toHaveValue(lost.publication.occurred_date)
 await expect(page.getByLabel('具体时间',{exact:true})).toHaveValue('')
 await page.getByRole('button',{name:'新一轮',exact:true}).click()
 const found=await say('我昨天晚上在田径场捡到一副黑色耳机，充电盒有一道划痕，帮我发布招领信息')
 expect(found.publication.kind).toBe('FOUND');expect(found.publication.title).toContain('拾到')
 await expect(page.locator('.agent-publication')).toBeVisible()
 expect(found.publication.location_candidate_ids.length).toBe(1)
 await expect(page.getByLabel('信息类型',{exact:true})).toHaveValue('FOUND')
 const clock=await say('具体时间是晚上九点半')
 expect(clock.publication.kind).toBe('FOUND');expect(clock.publication.occurred_at).toContain('21:30')
 await expect(page.getByLabel('具体时间',{exact:true})).toHaveValue('21:30')
 await page.route('**/assistant/agent/actions/',async route=>{const body=route.request().postDataJSON();writes++;expect(body.action).toBe('publish');expect(body.payload.kind).toBe('FOUND');expect(body.payload.location_candidate_ids.length).toBe(1);await route.fulfill({json:{data:{item:{id:'mock-found',title:body.payload.title,category_id:body.payload.category,review_status:'APPROVED'}}}})})
 await page.getByLabel('告诉小寻你记得的情况').fill('确认发布');await page.getByRole('button',{name:'发送 ↑'}).click()
 await expect(page.locator('.agent-task-panel')).toContainText('已帮你发布成功')
 expect(writes).toBe(1)
 await page.screenshot({path:'../artifacts/xun-date-found.png',fullPage:true})
})


test('demo photography loads locally in the gallery and has an honest detail caption',async({page})=>{
 await page.goto('/found')
 await expect(page.locator('.item-card').first()).toBeVisible()
 const image=page.locator('.item-card').filter({has:page.locator('img[src*="demo-reference"]')}).first()
 await expect(image).toBeVisible()
 const photo=image.locator('img').first()
 await expect.poll(()=>photo.evaluate((element:HTMLImageElement)=>element.complete&&element.naturalWidth>0)).toBe(true)
 await page.screenshot({path:'../artifacts/demo-photos-gallery.png',fullPage:true})
 await image.click()
 await expect(page.locator('.demo-photo-note')).toContainText('同类实物参考照片')
 await expect(page.locator('.item-photo--detail img')).toBeVisible()
 await page.screenshot({path:'../artifacts/demo-photos-detail.png',fullPage:true})
})
