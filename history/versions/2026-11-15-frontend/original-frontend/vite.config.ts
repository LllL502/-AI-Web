import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'

const apiTarget = process.env.CAMPUS_TRACE_API_TARGET ?? 'http://127.0.0.1:8000'
const sameOriginProxy = {
  '/api': { target: apiTarget, changeOrigin: false },
  '/media': { target: apiTarget, changeOrigin: false },
  '/_AMapService': { target: apiTarget, changeOrigin: false },
}
const publicTestHosts = ['.trycloudflare.com']
const previewCacheHeaders: Plugin = {
  name: 'campustrace-preview-cache-headers',
  configurePreviewServer(server) {
    server.middlewares.use((request, response, next) => {
      const path = (request.url ?? '').split('?', 1)[0] ?? ''
      // 构建产物带内容哈希，可长期缓存；插图保留稳定文件名，仅短时缓存便于更新。
      if (path.startsWith('/assets/')) response.setHeader('Cache-Control', 'public, max-age=31536000, immutable')
      else if (path.startsWith('/local-assets/')) response.setHeader('Cache-Control', 'public, max-age=3600, stale-while-revalidate=86400')
      next()
    })
  },
}

export default defineConfig({
  plugins: [vue(), previewCacheHeaders],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    allowedHosts: publicTestHosts,
    proxy: sameOriginProxy,
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
    allowedHosts: publicTestHosts,
    proxy: sameOriginProxy,
  },
  build: {
    target: 'es2022',
    sourcemap: true,
    chunkSizeWarningLimit: 850,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/three/')) return 'three'
          if (id.includes('/node_modules/echarts/') || id.includes('/node_modules/zrender/')) return 'echarts'
          if (id.includes('/node_modules/vue/') || id.includes('/node_modules/vue-router/') || id.includes('/node_modules/pinia/')) return 'vue'
          return undefined
        },
      },
    },
  },
})
