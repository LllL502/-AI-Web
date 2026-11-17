import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router, { warmPrimaryRoutes } from './router'
import { apiCached } from './api/client'
import './styles/tokens.css'
import './styles/global.css'
import './styles/assistant.css'
import './styles/product.css'

createApp(App).use(createPinia()).use(router).mount('#app')

function warmPublicExperience(): void {
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection
  if (connection?.saveData) return
  void warmPrimaryRoutes()
  // 首页和两个广场共用相同的短时缓存：空闲预取后，顶部切换不再重复等待接口。
  void apiCached('/items/?kind=FOUND').catch(() => undefined)
  void apiCached('/items/?kind=LOST').catch(() => undefined)
  void apiCached('/items/map-summary/').catch(() => undefined)
}

void router.isReady().then(() => {
  const browser = window as typeof window & {
    requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number
  }
  if (browser.requestIdleCallback) browser.requestIdleCallback(warmPublicExperience, { timeout: 2_000 })
  else window.setTimeout(warmPublicExperience, 1_000)
})
