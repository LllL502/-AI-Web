import {chromium} from '@playwright/test'
import fs from 'node:fs/promises'
import {fileURLToPath} from 'node:url'
const out = new URL('../../artifacts/backend-fixes/', import.meta.url)
await fs.mkdir(out, {recursive:true})
const browser = await chromium.launch({channel:'msedge', headless:true})
const page = await browser.newPage({locale:'zh-CN'})
const rows = []
let errors = [], failures = []
page.on('pageerror', error => errors.push(error.message))
page.on('response', response => {if(response.url().includes('/media/') && response.status() >= 400) failures.push({url:response.url(),status:response.status()})})
try {
  for(const role of ['guest', 'student']) {
    if(role === 'student') {
      await page.goto('http://127.0.0.1:5173/login')
      await page.getByLabel('用户名', {exact:true}).fill('student_01')
      await page.getByLabel('密码', {exact:true}).fill('CampusTrace!2026')
      await page.getByRole('button', {name:'登录',exact:true}).click()
      await page.waitForURL('**/home')
    }
    const response = await page.request.get('http://127.0.0.1:5173/api/v1/items/?kind=FOUND&page_size=1')
    const item = (await response.json()).data.items[0]
    for(const route of ['/home', '/found', '/lost', ...(item ? ['/items/'+item.id] : []), ...(role==='student' ? ['/me/items'] : [])]) {
      for(const width of [1280,390]) {
        errors = []; failures = []
        await page.setViewportSize({width,height:900})
        await page.goto('http://127.0.0.1:5173'+route, {waitUntil:'networkidle'})
        await page.locator('img').evaluateAll(async elements => {
          for(const image of elements) image.loading = 'eager'
          await Promise.all(elements.map(image => image.decode().catch(()=>{})))
        })
        const images = await page.locator('img').evaluateAll(elements => elements.filter(e=>e.src.includes('/media/')).map(e=>({src:e.src,loaded:e.complete&&e.naturalWidth>0})))
        rows.push({role, route, width, images, failures:[...failures], errors:[...errors]})
        if(route==='/home') await page.screenshot({path:fileURLToPath(new URL(`media-${role}-${width}.png`,out)),fullPage:true})
      }
    }
  }
} finally {
  await browser.close()
  await fs.writeFile(new URL('browser-media.json',out),JSON.stringify(rows,null,2))
}
const bad = rows.filter(row => row.errors.length || row.failures.length || row.images.some(image=>!image.loaded))
console.log(JSON.stringify({pages:rows.length,mediaImages:rows.reduce((sum,row)=>sum+row.images.length,0),failures:bad},null,2))
if(bad.length) process.exitCode=1
