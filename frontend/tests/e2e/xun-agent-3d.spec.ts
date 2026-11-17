import { expect,test } from '@playwright/test'

test('3D character shows its side and back during a dance turn without rotating the page',async({page})=>{
  await page.clock.install()
  await page.goto('/home')
  const character=page.locator('.agent-character')
  await character.scrollIntoViewIfNeeded()
  const model=character.locator('> .xun-agent')
  await expect(model).toHaveAttribute('data-renderer','webgl',{timeout:20_000})
  await expect(model.locator('canvas')).toBeVisible()
  await character.screenshot({path:'../artifacts/xun-3d-front.png'})
  for(let i=0;i<4;i++){
    await page.clock.fastForward(20_000)
    if((await model.getAttribute('class'))?.includes('spin'))break
  }
  await expect(model).toHaveClass(/spin/)
  await page.clock.runFor(1400)
  await character.screenshot({path:'../artifacts/xun-3d-turn-back.png'})
  await expect(character).toHaveCSS('transform','none')
  await expect(model).toHaveCSS('transform','none')
  await character.click()
  await expect(page.getByRole('dialog',{name:'和小寻一起找'})).toBeVisible()
})
