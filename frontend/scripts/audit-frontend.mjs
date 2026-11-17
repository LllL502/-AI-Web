import {chromium} from '@playwright/test'
import fs from 'node:fs/promises'
import {fileURLToPath} from 'node:url'
const out=new URL('../../artifacts/frontend-audit/',import.meta.url)
await fs.mkdir(out,{recursive:true})
const browser=await chromium.launch({channel:'msedge',headless:true})
const results=[]
const context=await browser.newContext({locale:'zh-CN',viewport:{width:1280,height:900}})
const page=await context.newPage()
let errors=[],failed=[]
page.on('pageerror',e=>errors.push(e.message))
page.on('response',r=>{if(r.status()>=400)failed.push({url:r.url(),status:r.status()})})
async function scan(route,width,role){
 errors=[];failed=[]
 await page.setViewportSize({width,height:900})
 try{
  await page.goto('http://127.0.0.1:5173'+route,{waitUntil:'networkidle',timeout:20000})
  const metrics=await page.evaluate(()=>{
   const visible=e=>{const b=e.getBoundingClientRect();return b.width>0&&b.height>0&&getComputedStyle(e).visibility!=='hidden'}
   const text=document.body.innerText
   return {title:document.title,h1:[...document.querySelectorAll('h1')].map(e=>e.innerText),width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
    overflow:[...document.querySelectorAll('main *,header *')].filter(e=>visible(e)&&e.getBoundingClientRect().right>innerWidth+2).slice(0,12).map(e=>({tag:e.tagName,cls:e.className,text:e.innerText?.slice(0,70),right:Math.round(e.getBoundingClientRect().right)})),
    unnamedControls:[...document.querySelectorAll('input:not([type=hidden]),textarea,select')].filter(e=>visible(e)&&!e.getAttribute('aria-label')&&!e.getAttribute('aria-labelledby')&&!e.labels?.length).map(e=>({tag:e.tagName,type:e.type,placeholder:e.placeholder})),
    unnamedButtons:[...document.querySelectorAll('button')].filter(e=>visible(e)&&!e.innerText.trim()&&!e.getAttribute('aria-label')&&!e.getAttribute('title')).map(e=>e.outerHTML.slice(0,150)),
    rawStatuses:text.match(/\b(?:APPROVED|PENDING|REJECTED|OPEN|CLOSED|RESERVED|RETURNED|USER|ACTIVE|STAFF|ADMIN|COMPLETED|SUBMITTED)\b/g),
    text:text.slice(0,1800)}
  })
  results.push({role,route,width,url:page.url(),errors:[...errors],failed:[...failed],...metrics})
  if(['/home','/found','/publish/found','/me','/me/items','/assistant','/admin/reviews'].includes(route))await page.screenshot({path:fileURLToPath(new URL(role+'-'+route.replaceAll('/','_')+'-'+width+'.png',out)),fullPage:true})
 }catch(e){results.push({role,route,width,error:String(e)})}
 await fs.writeFile(new URL('routes.json',out),JSON.stringify(results,null,2))
 console.log(role,width,route,results.at(-1).error??'checked')
}
for(const route of ['/home','/found','/lost','/search','/stations','/campus-map','/help','/login','/register','/recover','/missing-page'])for(const width of [1280,390])await scan(route,width,'guest')
async function login(username,url='/login'){
 await page.goto('http://127.0.0.1:5173'+url)
 await page.getByLabel('用户名',{exact:true}).fill(username)
 await page.getByLabel('密码',{exact:true}).fill('CampusTrace!2026')
 await page.getByRole('button',{name:url==='/admin-login'?'进入运营工作台':'登录',exact:true}).click()
 await page.waitForURL(url==='/admin-login'?'**/admin/overview':'**/home')
}
await login('student_01')
for(const route of ['/home','/assistant','/publish/lost','/publish/found','/drafts','/matches','/claims','/messages','/notifications','/me','/me/items','/me/favorites','/me/subscriptions','/me/settings','/stations/apply'])for(const width of [1280,390])await scan(route,width,'student')
const list=await page.request.get('http://127.0.0.1:5173/api/v1/items/?kind=FOUND&page_size=1');const item=(await list.json()).data.items[0]
if(item)for(const route of ['/items/'+item.id,'/claims/new/'+item.id])for(const width of [1280,390])await scan(route,width,'student')
await page.getByLabel('打开个人账户菜单').click();await page.getByRole('button',{name:'退出登录',exact:true}).click()
await login('admin_demo','/admin-login')
for(const route of ['/admin/overview','/admin/reviews','/admin/items','/admin/claims','/admin/users','/admin/stations','/admin/dictionaries','/admin/matching/config','/admin/matching/lab','/admin/reports','/admin/content','/admin/system'])for(const width of [1280,390])await scan(route,width,'admin')
await browser.close()
console.log('Audit complete:',results.length,'page/viewport combinations')
