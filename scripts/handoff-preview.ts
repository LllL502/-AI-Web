import type { Plugin } from 'vite'

export default function designPreview(): Plugin {
  const user = { id: -1, username: 'design_preview', display_name: '设计预览', role: 'USER', email: '' }
  const items = [
    { id: 'design-earbuds', title: '图书馆拾到黑色无线耳机', description: '黑色无线耳机与充电盒，盒盖有细小划痕。', category: 1, category_name: '耳机', brand: '', color: '黑色', image_url: '/design-assets/black-earbuds.png' },
    { id: 'design-umbrella', title: '教学楼拾到黑色折叠伞', description: '黑色折叠伞，伞柄带短挂绳。', category: 2, category_name: '雨伞', brand: '', color: '黑色', image_url: '/design-assets/black-umbrella.png' },
  ].map(item => ({ ...item, kind: 'FOUND', occurred_at: '2026-11-15T12:00:00+08:00', location_name: '图书馆', location: 1, business_status: 'OPEN', review_status: 'APPROVED', is_demo: true }))
  return {
    name: 'handoff-design-preview',
    configureServer(server) {
      if (process.env.CAMPUS_TRACE_DESIGN_PREVIEW !== '1') return
      server.middlewares.use(async (request, response, next) => {
        const url = new URL(request.url ?? '/', 'http://localhost')
        if (!url.pathname.startsWith('/api/')) return next()
        let raw = ''
        for await (const chunk of request) raw += chunk.toString()
        let input: any = {}
        try { input = JSON.parse(raw || '{}') } catch { }
        const path = url.pathname.replace('/api/v1', '')
        let data: any
        if (path === '/auth/csrf/') data = {}
        else if (['/auth/me/', '/auth/login/', '/auth/register/'].includes(path)) data = user
        else if (path === '/auth/logout/') data = {}
        else if (path === '/stations/campuses/') data = { items: [{ id: 1, name: '设计演示学校', province: '', city: '', is_demo: true, campuses: [{ id: 1, name: '演示校区', verification_status: 'VERIFIED' }] }], total: 1, page: 1, page_size: 20 }
        else if (path === '/items/metadata/') data = { categories: [{ id: 1, name: '耳机', code: 'electronics', parent_id: null }, { id: 2, name: '雨伞', code: 'daily', parent_id: null }], locations: [{ id: 1, name: '图书馆', code: 'design-library', parent_id: null }], stations: [] }
        else if (path === '/items/') data = { items, total: items.length, page: 1, page_size: 20 }
        else if (path === '/items/map-summary/') data = { locations: [] }
        else if (path.startsWith('/items/')) {
          const item = items.find(item => path === `/items/${item.id}/`)
          if (item) data = { ...item, media: [], location_candidates: [], coordinate_candidates: [] }
        }
        else if (path === '/assistant/capabilities/') data = { provider: { mode: 'development_stub', simulated: true, configured: true }, inputs: { text: true, image: true }, semantic_retrieval: false, guardrails: [] }
        else if (path === '/assistant/image/') data = { observation: '【设计预览样例】黑色无线耳机与充电盒；非实际图片识别结果。', persisted: false, requires_user_confirmation: true }
        else if (path === '/assistant/prepare/') data = { workflow_id: 'design-preview', provider: { name: 'development_stub', model: 'design-fixture', simulated: true }, draft: { kind: input.kind || 'LOST', title: '寻找黑色耳机', category_hint: '耳机', brand: '', colors: ['黑色'], occurred_at: null, location_hint: '', public_description: input.description || '设计预览样例', uncertain_fields: ['occurred_at'], source_spans: {} }, follow_up_questions: [{ field: 'occurred_at', question: '大约是什么时间遗失的？', reason: '设计预览', required: false }], stages: [{ id: 'extract', label: '整理物品信息', status: 'completed' }, { id: 'confirm', label: '确认物品信息', status: 'waiting' }] }
        else if (path === '/assistant/search/') data = { retrieval_method: 'design_fixture', semantic_retrieval: false, message: '设计预览样例，不是真实检索结果', candidates: items.map(item => ({ ...item, category: item.category_name, location: item.location_name, citation_id: `design:${item.id}`, url: `/items/${item.id}`, reasons: ['设计预览样例'], image_note: '合成演示配图', ranking: { score: .75, factors: { text: .7, category: 1, color: 1, brand: null, location: null, time: null }, penalty_multiplier: 1, conflicts: [] } })), stations: [], stages: [{ id: 'retrieve', label: '设计预览结果', status: 'completed' }] }
        else if (path === '/maps/config/') data = { web_key: '', service_host: '' }
        if (data === undefined) {
          response.statusCode = 501
          response.setHeader('Content-Type', 'application/json; charset=utf-8')
          return response.end(JSON.stringify({ error: { code: 'design_preview_unsupported', message: '该功能需连接真实后端；设计预览不执行发布、认领或审核。', fields: {} } }))
        }
        response.setHeader('Content-Type', 'application/json; charset=utf-8')
        response.end(JSON.stringify({ data }))
      })
    },
  }
}
