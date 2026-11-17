import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore, type UserRole } from '../stores/auth'
import HomeView from '../views/public/HomeView.vue'

const ItemGalleryView = () => import('../views/public/ItemGalleryView.vue')
const ItemDetailView = () => import('../views/public/ItemDetailView.vue')
const CampusMapView = () => import('../views/public/CampusMapView.vue')
const SearchView = () => import('../views/public/SearchView.vue')
const StationsView = () => import('../views/public/StationsView.vue')
const StationDetailView = () => import('../views/public/StationDetailView.vue')
const StationApplicationView = () => import('../views/public/StationApplicationView.vue')
const PublicContentView = () => import('../views/public/PublicContentView.vue')
const PublishView = () => import('../views/user/PublishView.vue')
const DraftsView = () => import('../views/user/DraftsView.vue')
const MatchCenterView = () => import('../views/user/MatchCenterView.vue')
const MatchReportView = () => import('../views/user/MatchReportView.vue')
const MatchCompareView = () => import('../views/user/MatchCompareView.vue')
const ClaimCreateView = () => import('../views/user/ClaimCreateView.vue')
const ClaimsListView = () => import('../views/user/ClaimsListView.vue')
const ClaimDetailView = () => import('../views/user/ClaimDetailView.vue')
const HandoverView = () => import('../views/user/HandoverView.vue')
const MessagesView = () => import('../views/user/MessagesView.vue')
const NotificationsView = () => import('../views/user/NotificationsView.vue')
const AccountHubView = () => import('../views/user/AccountHubView.vue')
const AdminOverviewView = () => import('../views/admin/AdminOverviewView.vue')
const StationManagementView = () => import('../views/admin/StationManagementView.vue')
const AdminResourceView = () => import('../views/admin/AdminResourceView.vue')
const FeaturePage = () => import('../views/FeaturePage.vue')
const LoginView = () => import('../views/system/LoginView.vue')
const RecoveryView = () => import('../views/system/RecoveryView.vue')
const NotFoundView = () => import('../views/system/NotFoundView.vue')

// 用户空闲时预取顶部导航最常用的轻量页面，消除第一次点击时等待 JS 分包的停顿。
// 图表与 3D 大包仍按需加载，不进入首屏主包。
export function warmPrimaryRoutes(): Promise<unknown[]> {
  return Promise.allSettled([ItemGalleryView(), CampusMapView(), SearchView(), MatchCenterView()])
}

type PageMeta = { pageId: string; title: string; description?: string; requiresAuth?: boolean; roles?: UserRole[]; layout?: string }
const feature = (path: string, pageId: string, title: string, description: string, meta: Partial<PageMeta> = {}): RouteRecordRaw => ({
  path,
  name: pageId,
  component: FeaturePage,
  meta: { pageId, title, description, ...meta },
})

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/home' },
  { path: '/home', name: 'P01', component: HomeView, meta: { pageId: 'P01', title: '首页' } },
  { path: '/lost', name: 'P02', component: ItemGalleryView, props: { kind: 'LOST' }, meta: { pageId: 'P02', title: '遗失广场' } },
  { path: '/found', name: 'P03', component: ItemGalleryView, props: { kind: 'FOUND' }, meta: { pageId: 'P03', title: '招领广场' } },
  { path: '/items/:id', name: 'P04', component: ItemDetailView, meta: { pageId: 'P04', title: '物品详情' } },
  { path: '/items/:id/edit', name: 'P04-edit', component: PublishView, props: route => ({ editId: String(route.params.id) }), meta: { pageId: 'P04-edit', title: '编辑发布', requiresAuth: true } },
  { path: '/search', name: 'P05', component: SearchView, meta: { pageId: 'P05', title: '全局搜索' } },
  { path: '/publish/lost', name: 'P06', component: PublishView, props: { kind: 'LOST' }, meta: { pageId: 'P06', title: '发布遗失', requiresAuth: true } },
  { path: '/publish/found', name: 'P07', component: PublishView, props: { kind: 'FOUND' }, meta: { pageId: 'P07', title: '发布招领', requiresAuth: true } },
  { path: '/drafts', name: 'P08', component: DraftsView, meta: { pageId: 'P08', title: '草稿箱', requiresAuth: true } },
  { path: '/matches', name: 'P09', component: MatchCenterView, meta: { pageId: 'P09', title: '智能匹配', requiresAuth: true } },
  { path: '/matches/runs/:runId', name: 'P10', component: MatchReportView, meta: { pageId: 'P10', title: '匹配报告', requiresAuth: true } },
  { path: '/matches/compare/:lostId/:foundId', name: 'P11', component: MatchCompareView, meta: { pageId: 'P11', title: '双物品对比', requiresAuth: true } },
  { path: '/campus-map', name: 'P12', component: CampusMapView, meta: { pageId: 'P12', title: '校园线索地图' } },
  { path: '/stations', name: 'P13', component: StationsView, meta: { pageId: 'P13', title: '服务站' } },
  { path: '/stations/:id', name: 'P14', component: StationDetailView, meta: { pageId: 'P14', title: '服务站详情' } },
  { path: '/stations/apply', name: 'P14-apply', component: StationApplicationView, meta: { pageId: 'P14-apply', title: '学校服务站接入', requiresAuth: true } },
  { path: '/claims/new/:foundId', name: 'P15', component: ClaimCreateView, meta: { pageId: 'P15', title: '发起认领', requiresAuth: true } },
  { path: '/claims', name: 'P16', component: ClaimsListView, meta: { pageId: 'P16', title: '我的认领', requiresAuth: true } },
  { path: '/claims/:id', name: 'P17', component: ClaimDetailView, meta: { pageId: 'P17', title: '认领详情', requiresAuth: true } },
  { path: '/handover/:claimId', name: 'P18', component: HandoverView, meta: { pageId: 'P18', title: '安全交接', requiresAuth: true } },
  { path: '/messages', name: 'P19', component: MessagesView, meta: { pageId: 'P19', title: '站内消息', requiresAuth: true } },
  { path: '/messages/:conversationId', name: 'P20', component: MessagesView, meta: { pageId: 'P20', title: '会话详情', requiresAuth: true } },
  { path: '/notifications', name: 'P21', component: NotificationsView, meta: { pageId: 'P21', title: '通知中心', requiresAuth: true } },
  { path: '/me', name: 'P22', component: AccountHubView, props: { mode: 'hub' }, meta: { pageId: 'P22', title: '个人中心', requiresAuth: true } },
  { path: '/me/items', name: 'P23', component: AccountHubView, props: { mode: 'items' }, meta: { pageId: 'P23', title: '我的发布', requiresAuth: true } },
  { path: '/me/favorites', name: 'P24', component: AccountHubView, props: { mode: 'favorites' }, meta: { pageId: 'P24', title: '我的收藏', requiresAuth: true } },
  { path: '/me/subscriptions', name: 'P25', component: AccountHubView, props: { mode: 'subscriptions' }, meta: { pageId: 'P25', title: '线索订阅', requiresAuth: true } },
  { path: '/me/settings', name: 'P26', component: AccountHubView, props: { mode: 'settings' }, meta: { pageId: 'P26', title: '账户设置', requiresAuth: true } },
  { path: '/help', name: 'P27', component: PublicContentView, meta: { pageId: 'P27', title: '帮助中心' } },
  { path: '/admin/overview', name: 'B01', component: AdminOverviewView, meta: { pageId: 'B01', title: '运营总览', requiresAuth: true, roles: ['STAFF', 'ADMIN'] } },
  { path: '/admin/reviews', name: 'B02', component: AdminResourceView, props: { mode: 'reviews' }, meta: { pageId: 'B02', title: '内容审核', requiresAuth: true, roles: ['STAFF', 'ADMIN'] } },
  { path: '/admin/items', name: 'B03', component: AdminResourceView, props: { mode: 'items' }, meta: { pageId: 'B03', title: '物品管理', requiresAuth: true, roles: ['STAFF', 'ADMIN'] } },
  { path: '/admin/claims', name: 'B04', component: AdminResourceView, props: { mode: 'claims' }, meta: { pageId: 'B04', title: '认领管理', requiresAuth: true, roles: ['STAFF', 'ADMIN'] } },
  { path: '/admin/users', name: 'B05', component: AdminResourceView, props: { mode: 'users' }, meta: { pageId: 'B05', title: '用户管理', requiresAuth: true, roles: ['ADMIN'] } },
  { path: '/admin/stations', name: 'B06', component: StationManagementView, meta: { pageId: 'B06', title: '站点管理', requiresAuth: true, roles: ['ADMIN'] } },
  { path: '/admin/dictionaries', name: 'B07', component: AdminResourceView, props: { mode: 'dictionaries' }, meta: { pageId: 'B07', title: '字典管理', requiresAuth: true, roles: ['ADMIN'] } },
  { path: '/admin/matching/config', name: 'B08', component: AdminResourceView, props: { mode: 'config' }, meta: { pageId: 'B08', title: '匹配参数中心', requiresAuth: true, roles: ['ADMIN'] } },
  { path: '/admin/matching/lab', name: 'B09', component: AdminResourceView, props: { mode: 'lab' }, meta: { pageId: 'B09', title: '算法实验室', requiresAuth: true, roles: ['ADMIN'] } },
  { path: '/admin/reports', name: 'B10', component: AdminResourceView, props: { mode: 'reports' }, meta: { pageId: 'B10', title: '报表中心', requiresAuth: true, roles: ['STAFF', 'ADMIN'] } },
  { path: '/admin/content', name: 'B11', component: AdminResourceView, props: { mode: 'content' }, meta: { pageId: 'B11', title: '内容运营', requiresAuth: true, roles: ['ADMIN'] } },
  { path: '/admin/system', name: 'B12', component: AdminResourceView, props: { mode: 'system' }, meta: { pageId: 'B12', title: '系统管理', requiresAuth: true, roles: ['ADMIN'] } },
  { path: '/login', name: 'login', component: LoginView, meta: { title: '登录', layout: 'system' } },
  { path: '/register', name: 'register', component: LoginView, props: { registerMode: true }, meta: { title: '注册', layout: 'system' } },
  { path: '/admin-login', name: 'admin-login', component: LoginView, props: { adminMode: true }, meta: { title: '管理端登录', layout: 'system' } },
  { path: '/recover', name: 'recover', component: RecoveryView, meta: { title: '找回账户', layout: 'system' } },
  { path: '/403', name: 'forbidden', component: NotFoundView, props: { statusCode: 403 }, meta: { title: '无权访问', layout: 'system' } },
  { path: '/500', name: 'server-error', component: NotFoundView, props: { statusCode: 500 }, meta: { title: '服务异常', layout: 'system' } },
  { path: '/offline', name: 'offline', component: NotFoundView, props: { statusCode: 0 }, meta: { title: '当前离线', layout: 'system' } },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundView, props: { statusCode: 404 }, meta: { title: '页面不存在', layout: 'system' } },
]

const router = createRouter({ history: createWebHistory(), routes, scrollBehavior: () => ({ top: 0 }) })

router.beforeEach(async (to) => {
  document.title = `${String(to.meta.title ?? '拾光')} · CampusTrace`
  const auth = useAuthStore()
  if (!auth.ready) {
    if(to.meta.requiresAuth||['login','register','admin-login'].includes(String(to.name)))await auth.bootstrap()
    else void auth.bootstrap()
  }
  if (to.meta.requiresAuth && !auth.user) return { name: 'login', query: { redirect: to.fullPath } }
  const roles = to.meta.roles as UserRole[] | undefined
  if (roles && auth.user && !roles.includes(auth.user.role)) return { name: 'forbidden' }
  if ((to.name === 'login' || to.name === 'register' || to.name === 'admin-login') && auth.user) return { name: 'P01' }
  return true
})

export default router
