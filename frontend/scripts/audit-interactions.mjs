import {chromium} from '@playwright/test'
import fs from 'node:fs/promises'
import {fileURLToPath} from 'node:url'
const folder=new URL('../../artifacts/frontend-audit/',import.meta.url)
await fs.mkdir(folder,{recursive:true})
const browser=await chromium.launch({channel:'msedge',headless:true})
const page=await browser.newPage({viewport:{width:1280,height:900},locale:'zh-CN'})
const evidence={};const errors=[];page.on('pageerror',e=>errors.push(e.message))
const go=path=>page.goto('http://127.0.0.1:5173'+path,{waitUntil:'networkidle'})
await go('/login');await page.getByLabel('用户名',{exact:true}).fill('student_01');await page.getByLabel('密码',{exact:true}).fill('CampusTrace!2026');await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL('**/home')
await go('/search')
const searching=page.waitForResponse(r=>r.url().includes('/api/v1/items/?')&&!r.url().includes('kind='))
await page.getByRole('button',{name:'搜索公开线索'}).click()
const payload=await(await searching).json()
evidence.search={serverTotal:payload.data.total,pageSize:payload.data.page_size,rendered:await page.locator('.result').count(),paginationButtons:await page.getByRole('button',{name:/下一页|上一页/}).count()}
await page.locator('.search-form select').nth(1).selectOption({index:1})
await page.getByRole('button',{name:'搜索公开线索'}).click();await page.waitForTimeout(150)
evidence.searchCategory={visibleError:await page.locator('.notice.error').innerText(),selectedCategory:await page.locator('.search-form select').nth(1).inputValue()}
const list=await(await page.request.get('http://127.0.0.1:5173/api/v1/items/?kind=FOUND&page_size=2')).json()
const [one,two]=list.data.items
await go('/items/'+one.id)
await page.evaluate(async id=>{const router=document.querySelector('#app').__vue_app__.config.globalProperties.$router;await router.push('/items/'+id)},two.id)
await page.waitForTimeout(250)
evidence.itemRouteReuse={firstId:one.id,targetId:two.id,url:page.url(),expectedTitle:two.title,renderedTitle:await page.locator('h1').innerText()}
await page.screenshot({path:fileURLToPath(new URL('stale-item-detail.png',folder))})
await go('/publish/found')
await page.evaluate(async()=>{const router=document.querySelector('#app').__vue_app__.config.globalProperties.$router;await router.push('/publish/lost')});await page.waitForTimeout(100)
evidence.publishKindReuse={url:page.url(),renderedHeading:await page.locator('h1').innerText()}
await go('/me/favorites')
await page.route('**/api/v1/items/favorites/*/',route=>route.request().method()==='DELETE'?route.fulfill({status:500,json:{error:{message:'审查测试：取消收藏失败'}}}):route.continue())
await page.getByRole('button',{name:'取消收藏'}).first().click();await page.waitForTimeout(200)
evidence.favoriteError={visibleError:await page.locator('.notice.error').count(),browserErrors:[...errors]}
await page.unroute('**/api/v1/items/favorites/*/')
const thread=id=>({id,subject:'审查会话'+id,item_id:null,item_title:null,claim_id:null,participants:[],messages:[{id,sender_name:'审查用户',body:'当前应显示会话'+id,is_system:false,created_at:new Date().toISOString()}],updated_at:new Date().toISOString()})
await page.route('**/api/v1/messages/?*',route=>route.fulfill({json:{data:{items:[thread(11),thread(12)]}}}))
await page.route('**/api/v1/messages/11/',route=>route.fulfill({json:{data:thread(11)}}))
await page.route('**/api/v1/messages/12/',route=>route.fulfill({status:403,json:{error:{message:'审查测试：会话无权限'}}}))
await go('/messages/11');await page.getByRole('button',{name:/审查会话12/}).click();await page.waitForTimeout(200)
evidence.messageError={url:page.url(),thread:await page.locator('.thread').innerText(),visibleError:await page.locator('.notice.error').count(),browserErrors:[...errors]}
await page.screenshot({path:fileURLToPath(new URL('stale-message-thread.png',folder))})
await page.unrouteAll({behavior:'wait'})
// Read real detail pages without creating or changing business records.
for(const [endpoint,path] of [['claims','/claims/'],['matches/runs','/matches/runs/'],['stations','/stations/']]){
 const response=await page.request.get('http://127.0.0.1:5173/api/v1/'+endpoint+'/?page_size=1');const json=await response.json();const row=json.data?.items?.[0]
 if(row){await go(path+row.id);evidence[endpoint]={url:page.url(),h1:await page.locator('h1').allInnerTexts(),errors:[...errors]}}
}
await page.setViewportSize({width:390,height:844});await go('/home');await page.locator('.agent-character').click()
await page.screenshot({path:fileURLToPath(new URL('mobile-agent-chat.png',folder))})
evidence.chatMobile=await page.locator('.xun-chat').evaluateAll(nodes=>nodes.map(e=>({width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height})))
await page.getByLabel('关闭聊天').click()
await go('/publish/lost');await page.getByLabel('标题 *',{exact:true}).fill('审查临时草稿标记')
await page.getByLabel('打开个人账户菜单').click();await page.getByRole('button',{name:'退出登录',exact:true}).click()
await go('/login');await page.getByLabel('用户名',{exact:true}).fill('admin_demo');await page.getByLabel('密码',{exact:true}).fill('CampusTrace!2026');await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL('**/home');await go('/publish/lost')
evidence.draftAcrossAccounts={currentUser:await page.locator('.account-name').innerText(),restoredTitle:await page.getByLabel('标题 *',{exact:true}).inputValue()}
await fs.writeFile(new URL('interactions.json',folder),JSON.stringify(evidence,null,2))
console.log(JSON.stringify(evidence,null,2));await browser.close()
