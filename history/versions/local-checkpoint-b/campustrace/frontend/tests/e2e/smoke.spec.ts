import { expect, test, type Page } from '@playwright/test'

const screenshots = '../artifacts/screenshots'

async function login(page: Page, username: string) {
  await page.goto('/login')
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码').fill('CampusTrace!2026')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/home$/)
}

async function logout(page: Page) {
  await page.getByLabel('打开个人账户菜单').click()
  await page.getByRole('button', { name: /退出/ }).click()
  await expect(page).toHaveURL(/\/home$/)
}

test('账户菜单可进入我的发布且智能匹配沿用同一登录会话', async ({ page }) => {
  await login(page, 'student_01')
  await page.getByLabel('打开个人账户菜单').click()
  await page.getByRole('link', { name: /我的发布/ }).click()
  await expect(page).toHaveURL(/\/me\/items$/)
  await expect(page.getByRole('heading', { name: '我的发布' })).toBeVisible()
  await expect(page.getByRole('link', { name: '查看', exact: true }).first()).toBeVisible()
  await expect(page.getByRole('link', { name: '编辑', exact: true }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: '删除', exact: true }).first()).toBeVisible()

  await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '智能匹配' }).click()
  await expect(page).toHaveURL(/\/matches$/)
  await expect(page.getByRole('heading', { name: '智能匹配' })).toBeVisible()
  await expect(page.getByRole('link', { name: '登录' })).toHaveCount(0)
})

test('公开首页、线索列表和隐私响应可用', async ({ page, request }) => {
  await page.goto('/home')
  await expect(page.getByRole('heading', { name: /校园\s*失物招领/ })).toBeVisible()
  await expect(page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name: '校园地图' })).toBeVisible()
  await page.screenshot({ path: `${screenshots}/P01-home-desktop.png`, fullPage: true })

  await page.goto('/lost')
  await expect(page.getByRole('heading', { name: '遗失广场' })).toBeVisible()
  await expect(page.locator('.item-card').first()).toBeVisible()
  await page.screenshot({ path: `${screenshots}/P02-lost-gallery.png`, fullPage: true })

  const response = await request.get('http://127.0.0.1:8000/api/v1/items/?kind=LOST&page_size=1')
  expect(response.ok()).toBeTruthy()
  const body = await response.json()
  const publicItem = body.data.items[0]
  expect(publicItem.location_detail).toBeUndefined()
  expect(publicItem.latitude).toBeUndefined()
  expect(publicItem.longitude).toBeUndefined()
  expect(`${publicItem.title} ${publicItem.description}`).not.toMatch(/\b(?:CT|U|V)\d{3}\b/)
})

test('公开搜索、服务站和帮助页读取真实数据', async ({ page }) => {
  await page.goto('/search')
  await expect(page.getByRole('heading', { name: '全局搜索' })).toBeVisible()
  await page.getByRole('button', { name: /搜索公开线索/ }).click()
  await expect(page.locator('.result').first()).toBeVisible()

  await page.goto('/stations')
  await expect(page.getByRole('heading', { name: '校园服务站' })).toBeVisible()
  await expect(page.locator('.station').first()).toBeVisible()

  await page.goto('/help')
  await expect(page.getByRole('heading', { name: '帮助中心' })).toBeVisible()
  await expect(page.locator('.entry').first()).toBeVisible()

  await expect(page.getByRole('link', { name: '找回故事' })).toHaveCount(0)
  await page.goto('/stories')
  await expect(page.getByText('404', { exact: true })).toBeVisible()
})

test('普通用户可进入匹配中心并真实生成候选', async ({ page }) => {
  await login(page, 'student_01')
  await page.goto('/matches')
  await expect(page.getByRole('heading', { name: '智能匹配' })).toBeVisible()
  const select = page.getByLabel('选择我的遗失信息')
  await expect(select.locator('option').filter({ hasText: 'APPROVED' }).first()).toBeAttached()
  const approvedValue = await select.locator('option').evaluateAll((options) => {
    const approved = options.find((option) => option.textContent?.includes('APPROVED')) as HTMLOptionElement | undefined
    return approved?.value ?? ''
  })
  expect(approvedValue).not.toBe('')
  await select.selectOption(approvedValue)
  await page.getByRole('button', { name: '发起匹配' }).click()
  await expect(page.locator('.run-row').first()).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('button', { name: '发起匹配' })).toBeEnabled()
  await page.screenshot({ path: `${screenshots}/P09-match-center.png`, fullPage: true })
  await page.locator('.run-row').first().click()
  await expect(page.getByRole('heading', { name: '匹配报告' })).toBeVisible()
  await expect(page.locator('.candidate').first()).toBeVisible()
  await page.locator('.candidate').first().getByRole('link', { name: /对比证据/ }).click()
  await expect(page.getByRole('heading', { name: '双物品证据对比' })).toBeVisible()
  await expect(page.locator('.coverage strong')).toContainText('证据覆盖度')
  await expect(page.getByRole('img', { name: '由真实匹配快照驱动的关系解释场景' }).or(page.getByRole('region', { name: /关系解释场景的二维回退/ }))).toBeVisible()
  await page.goto('/matches')
  await expect(page.locator('.three-shell')).toHaveCount(0)
})

test('个人空间、收藏与订阅读取当前用户数据', async ({ page }) => {
  await login(page, 'student_01')
  await page.goto('/me')
  await expect(page.getByRole('heading', { name: '个人中心' })).toBeVisible()
  await page.goto('/me/favorites')
  await expect(page.getByRole('heading', { name: '我的收藏' })).toBeVisible()
  await expect(page.locator('.row').first()).toBeVisible()
  await page.goto('/me/subscriptions')
  await expect(page.getByRole('heading', { name: '线索订阅', exact: true })).toBeVisible()
  await expect(page.locator('.subscription').first()).toBeVisible()
})

test('站内消息与通知按登录用户加载', async ({ page }) => {
  await login(page, 'student_03')
  await page.goto('/messages')
  await expect(page.getByRole('heading', { name: '站内消息' })).toBeVisible()
  await expect(page.locator('.inbox button').first()).toBeVisible()
  await page.locator('.inbox button').first().click()
  await expect(page.locator('.message-list article').first()).toBeVisible()
  await page.goto('/notifications')
  await expect(page.getByRole('heading', { name: '通知中心' })).toBeVisible()
  await expect(page.locator('.notice-list .notice').first()).toBeVisible()
})

test('其余前台业务路由读取真实对象并正常渲染', async ({ page }) => {
  await page.goto('/found')
  await expect(page.getByRole('heading', { name: '招领广场' })).toBeVisible()
  const foundId = await page.evaluate(async () => {
    const body = await fetch('/api/v1/items/?kind=FOUND&page_size=1').then((response) => response.json())
    return body.data.items[0].id as string
  })
  await page.goto(`/items/${foundId}`)
  await expect(page.locator('.detail-content h1')).toBeVisible()
  await page.goto(`/claims/new/${foundId}`)
  await expect(page).toHaveURL(/\/login\?redirect=/)

  await page.goto('/stations')
  await page.locator('.station').first().click()
  await expect(page).toHaveURL(/\/stations\/\d+$/)
  await expect(page.locator('.station-head h1')).toBeVisible()

  await login(page, 'student_03')
  await page.goto(`/claims/new/${foundId}`)
  await expect(page.getByRole('heading', { name: '发起认领核验' })).toBeVisible()
  for (const [path, heading] of [
    ['/publish/lost', '发布遗失线索'], ['/publish/found', '登记拾获物品'],
    ['/drafts', '草稿与审核进度'], ['/claims', '我的认领'],
    ['/me/items', '我的发布'], ['/me/settings', '账户设置'],
  ] as const) {
    await page.goto(path)
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
  }
  const claimId = await page.evaluate(async () => {
    const body = await fetch('/api/v1/claims/?page_size=100').then((response) => response.json())
    return body.data.items[0].id as string
  })
  await page.goto(`/claims/${claimId}`)
  await expect(page.locator('.detail h1')).toBeVisible()

  await logout(page)
  await login(page, 'student_05')
  const handoverClaimId = await page.evaluate(async () => {
    const body = await fetch('/api/v1/claims/?page_size=100').then((response) => response.json())
    return body.data.items.find((entry: { status: string }) => entry.status === 'HANDOVER_PENDING').id as string
  })
  await page.goto(`/handover/${handoverClaimId}`)
  await expect(page.getByRole('heading', { name: '安全交接' })).toBeVisible()
})

test('系统页面和权限恢复路径可达', async ({ page }) => {
  await page.goto('/register')
  await expect(page.getByRole('heading', { name: '创建校园账户' })).toBeVisible()
  await page.goto('/admin-login')
  await expect(page.getByRole('heading', { name: '进入运营工作台' })).toBeVisible()
  await page.goto('/recover')
  await expect(page.getByRole('heading', { name: '找回校园账户' })).toBeVisible()
  for (const [path, heading] of [
    ['/403', '此区域需要相应权限'], ['/500', '服务暂时没有回应'],
    ['/offline', '当前处于离线状态'], ['/does-not-exist', '这条线索不在这里'],
  ] as const) {
    await page.goto(path)
    await expect(page.getByRole('heading', { name: heading })).toBeVisible()
  }
})

test('管理员总览和 11 个后台模块均由真实接口驱动', async ({ page }) => {
  await login(page, 'admin_demo')
  await page.goto('/admin/overview')
  await expect(page.getByRole('heading', { name: '运营总览' })).toBeVisible()
  await expect(page.getByRole('img', { name: '真实物品审核状态柱状图' })).toBeVisible()
  await page.screenshot({ path: `${screenshots}/B01-admin-overview.png`, fullPage: true })

  const modules = [
    ['/admin/reviews', '内容审核'], ['/admin/items', '物品管理'], ['/admin/claims', '认领管理'],
    ['/admin/users', '用户管理'], ['/admin/stations', '站点管理'], ['/admin/dictionaries', '字典管理'],
    ['/admin/matching/config', '匹配参数中心'], ['/admin/matching/lab', '算法实验室'],
    ['/admin/reports', '报表中心'], ['/admin/content', '内容运营'], ['/admin/system', '系统管理'],
  ] as const
  for (const [path, heading] of modules) {
    await page.goto(path)
    await expect(page.getByRole('heading', { name: heading })).toBeVisible()
    await expect(page.locator('.state')).toHaveCount(0)
  }
  await page.goto('/admin/matching/lab')
  await expect(page.locator('.lab-summary')).toBeVisible()
  await page.screenshot({ path: `${screenshots}/B09-algorithm-lab.png`, fullPage: true })
})

test('手机视口无水平溢出并保留二维或三维场景', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/campus-map')
  await expect(page.getByRole('heading', { name: '校园线索地图' })).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1)
  expect(overflow).toBeFalsy()
  await page.screenshot({ path: `${screenshots}/P12-campus-map-mobile.png`, fullPage: true })
})
