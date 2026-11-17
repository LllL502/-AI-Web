import {expect,test,type Page} from '@playwright/test'

async function login(page:Page,username='student_01'){
 await page.goto('/login');await page.getByLabel('用户名',{exact:true}).fill(username);await page.getByLabel('密码',{exact:true}).fill('CampusTrace!2026');await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL('**/home')
}

test('search filters numeric IDs, updates the URL and reaches later results',async({page})=>{
 await page.goto('/search')
 await expect(page.locator('.result').first()).toBeVisible()
 await expect(page.getByRole('button',{name:'下一页',exact:true})).toBeVisible()
 await page.getByRole('button',{name:'下一页',exact:true}).click();await expect(page).toHaveURL(/page=2/)
 await expect(page.locator('.list-pager')).toContainText('第 2 /')
 await page.locator('.search-form select').nth(1).selectOption({index:1})
 const response=page.waitForResponse(r=>r.url().includes('/api/v1/items/?')&&r.url().includes('category='))
 await page.getByRole('button',{name:'搜索公开线索'}).click();expect((await response).ok()).toBe(true)
 await expect(page.locator('.notice.error')).toHaveCount(0)
 await page.reload();await expect(page.locator('.search-form select').nth(1)).not.toHaveValue('')
})

test('changing detail IDs and publication kinds cannot reuse the old record',async({page})=>{
 await login(page)
 const response=await page.request.get('/api/v1/items/?kind=FOUND&page_size=2');const [one,two]=(await response.json()).data.items
 await page.goto('/items/'+one.id)
 await page.evaluate(async id=>{const router=(document.querySelector('#app') as any).__vue_app__.config.globalProperties.$router;await router.push('/items/'+id)},two.id)
 await expect(page.locator('h1')).toHaveText(two.title)
 await page.goto('/publish/found')
 await page.evaluate(async()=>{const router=(document.querySelector('#app') as any).__vue_app__.config.globalProperties.$router;await router.push('/publish/lost')})
 await expect(page.locator('h1')).toContainText(/遗失|寻物/)
})

test('unowned legacy drafts are ignored and different accounts keep different drafts',async({page})=>{
 await login(page)
 await page.evaluate(()=>localStorage.setItem('campustrace-draft-demo-lost',JSON.stringify({title:'不应导入的旧草稿'})))
 await page.goto('/publish/lost');await expect(page.getByLabel('标题 *',{exact:true})).toHaveValue('')
 await page.getByLabel('标题 *',{exact:true}).fill('学生自己的未提交草稿')
 await page.getByLabel('打开个人账户菜单').click();await page.getByRole('button',{name:'退出登录',exact:true}).click()
 await login(page,'admin_demo');await page.goto('/publish/lost')
 await expect(page.getByLabel('标题 *',{exact:true})).toHaveValue('')
})

test('a failed conversation switch cannot retain the previous sender target',async({page})=>{
 await login(page)
 const thread=(id:number)=>({id,subject:'回归会话'+id,item_id:null,item_title:null,claim_id:null,participants:[],messages:[{id,sender_name:'测试',body:'消息'+id,is_system:false,created_at:new Date().toISOString()}],updated_at:new Date().toISOString()})
 await page.route('**/api/v1/messages/?*',r=>r.fulfill({json:{data:{items:[thread(11),thread(12)]}}}))
 await page.route('**/api/v1/messages/11/',r=>r.fulfill({json:{data:thread(11)}}))
 await page.route('**/api/v1/messages/12/',r=>r.fulfill({status:403,json:{error:{message:'无权打开这条会话'}}}))
 await page.goto('/messages/11');await expect(page.locator('.thread')).toContainText('消息11')
 await page.getByRole('button',{name:/回归会话12/}).click()
 await expect(page.getByText('无权打开这条会话').first()).toBeVisible()
 await expect(page.locator('.thread textarea')).toHaveCount(0)
 await expect(page.locator('.thread')).not.toContainText('消息11')
})

test('failed favorite removal is visible and does not remove the record',async({page})=>{
 await login(page);await page.goto('/me/favorites')
 await expect(page.getByRole('button',{name:'取消收藏',exact:true}).first()).toBeVisible()
 const before=await page.getByRole('button',{name:'取消收藏',exact:true}).count()
 expect(before).toBeGreaterThan(0)
 await page.route('**/api/v1/items/favorites/*/',r=>r.request().method()==='DELETE'?r.fulfill({status:500,json:{error:{message:'暂时无法取消收藏'}}}):r.continue())
 await page.getByRole('button',{name:'取消收藏',exact:true}).first().click()
 await expect(page.locator('.notice.error')).toContainText('暂时无法取消收藏')
 await expect(page.getByRole('button',{name:'取消收藏',exact:true})).toHaveCount(before)
})

test('AI entry opens the same agent and mobile controls have readable labels',async({page})=>{
 await login(page);await page.setViewportSize({width:390,height:844});await page.goto('/assistant')
 await page.locator('.assistant-entry>.button').click()
 await expect(page.getByRole('dialog',{name:'和小寻一起找'})).toBeVisible()
 await expect(page.getByLabel('告诉小寻你记得的情况')).toBeVisible()
 await page.getByLabel('关闭聊天').click()
 await expect(page.getByLabel('上传物品照片用于识别')).toBeVisible()
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})

test('admin navigation exposes all modules and review includes material plus a real reason',async({page})=>{
 await login(page,'admin_demo');await page.goto('/admin/overview')
 const navigation=page.getByRole('navigation',{name:'运营管理导航'})
 await expect(navigation.getByRole('link')).toHaveCount(12)
 await expect(page.locator('body')).not.toContainText('当前门禁诚实状态')
 await navigation.getByRole('link',{name:'内容审核',exact:true}).click()
 const button=page.getByRole('button',{name:'查看审核材料'}).first()
 await expect(button).toBeVisible();await button.click()
 const dialog=page.getByRole('dialog',{name:'发布内容审核'})
 await expect(dialog.locator('.review-description')).not.toBeEmpty()
 await dialog.getByLabel('审核决定',{exact:true}).selectOption('REJECT')
 await expect(dialog.getByLabel('审核说明',{exact:true})).toHaveAttribute('required','')
 let note=''
 await page.route('**/api/v1/items/*/review/',async r=>{note=r.request().postDataJSON().note;await r.fulfill({json:{data:{}}})})
 await dialog.getByLabel('审核说明',{exact:true}).fill('回归测试：请补充清晰物品照片')
 await dialog.getByRole('button',{name:'确认提交审核决定'}).click()
 await expect(dialog).toHaveCount(0);expect(note).toBe('回归测试：请补充清晰物品照片')
})


for(const width of [320,768])test('key pages and campus picker remain usable at '+width+'px',async({page})=>{
 await login(page);await page.setViewportSize({width,height:900})
 for(const path of ['/home','/assistant','/publish/found','/me/items']){await page.goto(path);await expect(page.locator('h1')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),path).toBe(true)}
 await page.locator('.campus-trigger').click();await expect(page.getByRole('dialog',{name:'学校与校区'})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true)
})

test('coordinator navigation only shows authorized operational modules',async({page})=>{
 await login(page,'staff_east');await page.goto('/admin/overview')
 const nav=page.getByRole('navigation',{name:'运营管理导航'})
 await expect(nav.getByRole('link')).toHaveCount(5)
 await expect(nav.getByRole('link',{name:'用户管理',exact:true})).toHaveCount(0)
 await expect(page.getByRole('link',{name:'系统与审计',exact:true})).toHaveCount(0)
})
