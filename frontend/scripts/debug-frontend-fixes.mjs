import {chromium} from '@playwright/test'
const browser=await chromium.launch({channel:'msedge',headless:true})
const page=await browser.newPage({viewport:{width:390,height:844}})
await page.goto('http://127.0.0.1:5173/found',{waitUntil:'networkidle'})
const response=await page.request.get('http://127.0.0.1:5173/api/v1/items/?kind=FOUND&page_size=2')
const [a,b]=(await response.json()).data.items
await page.goto('http://127.0.0.1:5173/items/'+a.id,{waitUntil:'networkidle'})
console.log(await page.evaluate(async id=>{const imported=(await import('/src/router/index.ts')).default;const actual=document.querySelector('#app').__vue_app__.config.globalProperties.$router;const same=actual===imported;await actual.push('/items/'+id);return {same,actualPath:actual.currentRoute.value.path,importedPath:imported.currentRoute.value.path}},b.id))
await page.waitForTimeout(500);console.log('title',await page.locator('h1').innerText(),'expected',b.title)
await page.goto('http://127.0.0.1:5173/login');await page.getByLabel('用户名',{exact:true}).fill('student_01');await page.getByLabel('密码',{exact:true}).fill('CampusTrace!2026');await page.getByRole('button',{name:'登录',exact:true}).click();await page.waitForURL('**/home');await page.goto('http://127.0.0.1:5173/assistant',{waitUntil:'networkidle'})
console.log('overflow',await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,elements:[...document.querySelectorAll('body *')].filter(e=>{const b=e.getBoundingClientRect();return b.width&&b.right>innerWidth+2}).slice(0,20).map(e=>({cls:e.className,tag:e.tagName,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right,text:e.innerText?.slice(0,45)}))})))
await browser.close()
