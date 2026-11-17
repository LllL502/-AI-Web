import {test,expect} from '@playwright/test'
async function admin(page:any){await page.goto('/admin-login');await page.getByLabel('用户名',{exact:true}).fill('admin_demo');await page.getByLabel('密码',{exact:true}).fill('CampusTrace!2026');await page.getByRole('button',{name:'进入运营工作台',exact:true}).click();await page.waitForURL('**/admin/overview')}
test('admin can copy, edit and publish a version while historical contents stay frozen',async({page})=>{
 await admin(page)
 let rows:any[]=[{id:1,name:'历史配置',version:'audit-history',weights:{text:.5,category:.15,location:.12,time:.1,color:.08,brand:.05},thresholds:{min_score:.4},preprocessing:{dictionary_version:'campus-dict-v1',aliases:{校图:'图书馆'}},state:'HISTORICAL',editable:false,is_published:false}]
 const writes:any[]=[]
 await page.route('**/api/v1/admin/matching-configs/**',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname
  if(request.method()==='GET'){await route.fulfill({json:{data:{items:rows,total:rows.length,page:1,page_size:100}}});return}
  writes.push({path,body:request.postDataJSON(),method:request.method()})
  if(path.endsWith('/publish/')){rows=rows.map(row=>row.id===2?{...row,state:'ACTIVE',is_published:true,editable:false}:row)}
  else if(request.method()==='POST')rows.push({...request.postDataJSON(),id:2,state:'DRAFT',editable:true,is_published:false})
  else rows=rows.map(row=>row.id===2?{...row,...request.postDataJSON()}:row)
  await route.fulfill({json:{data:{}}})
 })
 await page.goto('/admin/matching/config')
 await expect(page.getByText('历史已发布',{exact:true})).toBeVisible()
 await expect(page.getByRole('button',{name:'编辑草稿'})).toHaveCount(0)
 await page.getByRole('button',{name:'基于此版本新建'}).click()
 await page.getByLabel('版本号',{exact:true}).fill('audit-v2')
 await page.getByRole('button',{name:'保存草稿'}).click()
 await expect(page.getByText('audit-v2',{exact:true})).toBeVisible()
 expect(writes[0].body.weights).toEqual(rows[0].weights)
 expect(writes[0].body.preprocessing.aliases).toEqual({校图:'图书馆'})
 await page.getByRole('button',{name:'编辑草稿'}).click()
 await page.getByLabel('配置名称',{exact:true}).fill('第二版参数')
 await page.getByRole('button',{name:'保存草稿'}).click()
 page.once('dialog',dialog=>dialog.accept())
 await page.getByRole('button',{name:'发布',exact:true}).click()
 await expect(page.getByText('当前使用',{exact:true})).toBeVisible()
 expect(writes.map(write=>write.method)).toEqual(['POST','PATCH','POST'])
 expect(writes.every(write=>!write.path.includes('/1/'))).toBe(true)
 for(const width of [1280,390]){await page.setViewportSize({width,height:900});await page.getByRole('button',{name:'新建版本',exact:true}).click();await expect(page.getByLabel('版本号',{exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:`../artifacts/ten-fixes/config-${width}.png`,fullPage:true});await page.getByRole('button',{name:'取消',exact:true}).click()}
})
test('system page displays a voice outage instead of reporting all AI services ready',async({page})=>{
 await admin(page)
 await page.route('**/api/v1/assistant/health/',route=>route.fulfill({json:{data:{models:{extraction:{ready:true,state:'available'},embedding:{ready:true,state:'available'},vision:{ready:true,state:'available'},voice:{ready:false,state:'unavailable'}}}}}))
 await page.goto('/admin/system')
 await expect(page.getByText('小寻童声',{exact:true})).toBeVisible()
 await expect(page.getByText('服务未启动',{exact:true})).toBeVisible()
})
