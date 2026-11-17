import { expect, test } from '@playwright/test'

for (const width of [390, 1440]) {
  test(`refreshed home and assistant at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 })
    await page.goto('/home')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('你在找的')
    await expect(page.locator('.entry-board')).toHaveCSS('transform', 'none')
    await expect(page.getByRole('link', { name: '开始 AI 寻物' })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true)
    await page.screenshot({ path: `../artifacts/refresh-home-${width}.png`, fullPage: true })
    await page.goto('/login?redirect=/assistant')
    await page.getByLabel('用户名', { exact: true }).fill('student_01')
    await page.getByLabel('密码', { exact: true }).fill('CampusTrace!2026')
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page.locator('.workspace-welcome')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true)
    await page.screenshot({ path: `../artifacts/refresh-assistant-${width}.png`, fullPage: true })
  })
}
