import {expect,test} from '@playwright/test'
import fs from 'node:fs/promises'
test('card name/student-number presence continues chat and offers five ranked possible places',async({page})=>{
 test.skip(process.env.CAMPUSTRACE_REAL_LOCAL_AI!=='1','Requires local models')
 test.setTimeout(240_000)
 await page.goto('/login?redirect=/home')
 await page.getByLabel('用户名',{exact:true}).fill('student_01')
 await page.getByLabel('密码',{exact:true}).fill('CampusTrace!2026')
 await page.getByRole('button',{name:'登录',exact:true}).click()
 await page.locator('.agent-character').click()
 const audit:any[]=[]
 async function say(text:string){
  const next=page.waitForResponse(r=>r.url().endsWith('/assistant/conversation/')&&r.request().method()==='POST',{timeout:100_000})
  await page.getByLabel('告诉小寻你记得的情况').fill(text)
  await page.getByRole('button',{name:'发送 ↑'}).click()
  const r=await next;const body=await r.json();expect(r.status(),JSON.stringify(body.error)).toBe(200)
  const d=body.data;audit.push({user:text,reply:d.reply,description:d.description,draft:d.draft,publication:d.publication})
  await fs.writeFile('../artifacts/xun-card-identity-audit.json',JSON.stringify(audit,null,2))
  await expect(page.locator('.chat-thinking')).toHaveCount(0)
  return d
 }
 await say('你好')
 await say('我丢了一个学生卡')
 const blue=await say('蓝色的，不知道在哪里丢的')
 expect(blue.draft.colors.join('')).toContain('蓝色')
 const identity=await say('有我的名字还有学号等信息')
 expect(identity.draft.colors.join('')).toContain('蓝色')
 expect(identity.draft.identity_markers).toEqual(['name','student_number'])
 await expect(page.locator('.chat-error')).toHaveCount(0)
 await page.getByRole('button',{name:'帮我发布寻物信息',exact:true}).click()
 const venues=identity.options.candidate_locations as {id:number;name:string}[]
 expect(venues.length).toBeGreaterThanOrEqual(6)
 const picker=page.getByRole('region',{name:'可能地点选择'})
 // The semantic section is labelled, but may be exposed as a generic section.
 const scope=page.locator('.agent-location-picker')
 for(const venue of venues.slice(0,5))await scope.getByRole('button',{name:venue.name,exact:true}).click()
 await expect(scope.locator('.location-ranking li')).toHaveCount(5)
 await scope.getByRole('button',{name:venues[5]!.name,exact:true}).click()
 await expect(scope.locator('.location-ranking li')).toHaveCount(5)
 await expect(page.locator('.agent-action-error')).toContainText('最多选择5个')
 await scope.getByRole('button',{name:'提高地点可能性排名'}).nth(1).click()
 await expect(scope.locator('.location-ranking li').first()).toContainText(venues[1]!.name)
 await page.screenshot({path:'../artifacts/xun-card-five-places.png',fullPage:true})
})
