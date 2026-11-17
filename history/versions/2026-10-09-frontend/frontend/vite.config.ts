import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const apiTarget = process.env.CAMPUS_TRACE_API_TARGET ?? 'http://127.0.0.1:8000'
const sameOriginProxy = {
  '/api': { target: apiTarget, changeOrigin: false },
  '/media': { target: apiTarget, changeOrigin: false },
  '/_AMapService': { target: apiTarget, changeOrigin: false },
}
const publicTestHosts = ['.trycloudflare.com']

export default defineConfig({
  plugins: [vue()],
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
