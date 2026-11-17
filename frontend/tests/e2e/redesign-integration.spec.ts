import { expect, test } from '@playwright/test'
import path from 'node:path'

test('homepage search carries real query and retrieves public items', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/home')
  await expect(page.locator('.preview-card').first()).toBeVisible()
  await page.getByRole('textbox', { name: '搜索校园物品' }).fill('耳机')
  await page.locator('.hero-search').getByRole('button', { name: '搜索', exact: true }).click()
  await expect(page).toHaveURL(/\/search\?q=/)
  await expect(page.getByPlaceholder('例如：黑色耳机 图书馆')).toHaveValue('耳机')
  await expect(page.locator('.result').first()).toBeVisible()
  expect(errors).toEqual([])
})

test('homepage photo survives login redirect and reaches AI confirmation flow', async ({ page }) => {
  await page.goto('/home')
  await page.getByRole('tab', { name: '上传照片' }).click()
  await page.locator('#home-ai-image').setInputFiles(path.resolve('../data/demo-images/black-earbuds.png'))
  await page.getByRole('button', { name: '我捡到物品' }).click()
  await page.getByRole('button', { name: 'AI 智能匹配线索' }).click()
  await expect(page).toHaveURL(/\/login\?redirect=/)
  await page.getByLabel('用户名', { exact: true }).fill('student_01')
  await page.getByLabel('密码', { exact: true }).fill('CampusTrace!2026')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/assistant/)
  await expect(page.locator('.selected-image-name')).toContainText('black-earbuds.png')
  await expect(page.getByRole('radio', { name: '我拾到物品' })).toBeChecked()
  await expect(page.getByRole('button', { name: '理解图片', exact: true })).toBeEnabled()
})
