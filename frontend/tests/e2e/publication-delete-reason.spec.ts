import {expect,test} from '@playwright/test'
test('protected deletion keeps the listing and explains the linked claim',async({page})=>{
 // Only the error/UI contract is simulated; no real publication is deleted.
 const reason='该信息已关联认领申请，不能删除。关闭线索后可从广场下架，认领记录仍会保留。'
 await page.route(url=>url.pathname==='/api/v1/items/'&&url.searchParams.get('mine')==='true',route=>route.fulfill({json:{data:{items:[{id:'protected-item',title:'已关闭的耳机线索',kind:'LOST',review_status:'APPROVED',business_status:'CLOSED',updated_at:'2026-11-16T12:00:00Z',allowed_actions:['delete']}]}}}))
 let attempts=0
 await page.route('**/api/v1/items/protected-item/',route=>{attempts++;return route.fulfill({status:400,json:{error:{code:'invalid',message:reason,fields:{non_field_errors:[reason]},request_id:'delete-reason-test'}}})})
 await page.goto('/login?redirect=/me/items')
 await page.getByLabel('用户名',{exact:true}).fill('student_01')
 await page.getByLabel('密码',{exact:true}).fill('CampusTrace!2026')
 await page.getByRole('button',{name:'登录',exact:true}).click()
 await expect(page).toHaveURL(/\/me\/items$/)
 page.on('dialog',d=>d.accept())
 await page.getByRole('button',{name:'删除',exact:true}).click()
 await expect(page.locator('.notice.error')).toHaveText(reason)
 await expect(page.getByRole('link',{name:'已关闭的耳机线索',exact:true})).toBeVisible()
 expect(attempts).toBe(1)
 await page.screenshot({path:'../artifacts/protected-publication-delete-reason.png',fullPage:true})
})
