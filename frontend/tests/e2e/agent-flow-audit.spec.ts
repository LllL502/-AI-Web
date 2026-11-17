import { expect, test } from '@playwright/test'

// UI wiring uses fixed responses; backend permissions/state transitions are
// separately exercised against the real test database. No demo claims are sent.
test('chat UI completes publication, claim, supplementary proof and handover without leaving home',async({page})=>{
  const actions:{action:string;payload:Record<string,unknown>;confirmed:boolean;key:string}[]=[]
  const prompts:unknown[]=[]
  let statusReads=0
  const claim=(status:string,allowed_actions:string[]=[])=>({id:'claim-audit',item_title:'粉色A4本子',status,allowed_actions})
  await page.route('**/api/v1/assistant/conversation/',async route=>{
    prompts.push(route.request().postDataJSON())
    await route.fulfill({json:{data:{stage:'results',description:'粉色A4本子，比较新。',reply:'已检索真实线索',
      candidates:[{id:'found-audit',title:'粉色A4本子',description:'封面没有贴纸',category_id:1,location:'教学楼',color:'粉色',brand:''}],
      publication:{kind:'LOST',title:'遗失粉色本子',description:'粉色A4本子，比较新。',category:1,location:2,occurred_at:'',brand:'',color:'粉色'},
      options:{categories:[{id:1,name:'纸质笔记本'}],locations:[{id:2,name:'教学楼'}]},owned_lost:[],tool_trace:[{tool:'query_public_items',status:'completed'}]}}})
  })
  await page.route('**/api/v1/assistant/agent/actions/',async route=>{
    const body=route.request().postDataJSON();actions.push(body)
    const result:Record<string,unknown>={}
    if(body.action==='publish')result.item={id:'lost-audit',title:'遗失粉色本子',category_id:1,review_status:'APPROVED'}
    if(body.action==='claim')result.claim=claim('SUBMITTED')
    if(body.action==='supplement')result.claim=claim('SUBMITTED')
    if(body.action==='status'){
      statusReads++
      result.claim=statusReads===1?{...claim('NEEDS_INFO'),decision_note:'请补充第三页细节'}:statusReads===2?claim('APPROVED',['start_direct_handover']):claim('COMPLETED')
    }
    if(body.action==='start_handover')result.claim=claim('HANDOVER_PENDING',['confirm_direct_handover'])
    if(body.action==='confirm_handover')result.claim=claim('HANDOVER_PENDING')
    await route.fulfill({json:{data:result}})
  })
  await page.goto('/login?redirect=/home')
  await page.getByLabel('用户名',{exact:true}).fill('student_01')
  await page.getByLabel('密码',{exact:true}).fill('CampusTrace!2026')
  await page.getByRole('button',{name:'登录',exact:true}).click()
  await page.locator('.agent-character').click()
  await page.getByLabel('告诉小寻你记得的情况').fill('我丢了粉色A4本子，比较新。')
  await page.getByRole('button',{name:'发送 ↑'}).click()
  await page.getByRole('button',{name:'查看并核对这件物品'}).click()
  await page.getByRole('button',{name:'帮我登记遗失信息'}).click()
  expect(actions).toHaveLength(0)
  await page.getByLabel('事件日期',{exact:true}).fill('2026-11-15')
  await page.getByLabel('具体时间',{exact:true}).fill('14:00')
  await page.getByRole('button',{name:'确认以上信息，提交发布'}).click()
  await expect(page.getByLabel('关联你的遗失信息')).toBeVisible()
  await page.getByLabel('告诉小寻你记得的情况').fill('核验特征：第三页写着一行只有我知道的字')
  await page.getByRole('button',{name:'发送 ↑'}).click()
  await expect(page.getByLabel('私密核验特征',{exact:true})).toHaveValue(/第三页/)
  expect(prompts).toHaveLength(1)
  await page.getByRole('button',{name:'确认是我的，提交认领申请'}).click()
  await expect(page.locator('.agent-claim-progress')).toContainText('等待对方核验')
  await page.getByRole('button',{name:'查看最新进度和消息'}).click()
  await expect(page.locator('.agent-claim-progress')).toContainText('需要补充证明')
  await page.getByLabel('补充私密核验特征').fill('第三页写着我自编的六位编号，边角还有蓝色标记')
  await page.getByRole('button',{name:'确认补充并提交核验'}).click()
  await expect(page.locator('.agent-claim-progress')).toContainText('等待对方核验')
  await page.getByRole('button',{name:'查看最新进度和消息'}).click()
  await page.getByRole('button',{name:'确认选择双方直接交接'}).click()
  await page.getByRole('button',{name:'我已拿到实物，确认我的交接'}).click()
  await expect(page.locator('.agent-claim-progress')).toContainText('等待实物交接')
  await page.getByRole('button',{name:'查看最新进度和消息'}).click()
  await expect(page.locator('.agent-claim-progress')).toContainText('已完成找回')
  await expect(page).toHaveURL(/\/home$/)
  for(const action of actions.filter(a=>a.action!=='status'))expect(action.confirmed).toBe(true)
  expect(actions.filter(a=>a.action==='publish')).toHaveLength(1)
  expect(actions.filter(a=>a.action==='claim')).toHaveLength(1)
  await page.screenshot({path:'../artifacts/xun-agent-flow-audit.png',fullPage:true})
})
