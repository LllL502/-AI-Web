<script setup lang="ts">
import { computed, ref } from 'vue'
import { campusRevision, campusSwitching } from './stores/campus'
import CampusPicker from './components/CampusPicker.vue'
import AdminNav from './components/AdminNav.vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import AppIcon from './components/AppIcon.vue'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const isSystemPage = computed(() => route.meta.layout === 'system')
const accountMenu = ref<HTMLDetailsElement | null>(null)
const userInitial = computed(() => auth.user?.display_name?.trim().slice(0, 1) || '同')

function closeAccountMenu() {
  if (accountMenu.value) accountMenu.value.open = false
}

async function signOut() {
  closeAccountMenu()
  await auth.logout()
  await router.push('/home')
}
</script>

<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a>
  <div v-if="isSystemPage" class="system-layout">
    <RouterView v-if="!campusSwitching" v-slot="{Component}"><component :is="Component" :key="`${campusRevision}:${auth.user?.id??'guest'}:${route.path}`"/></RouterView>
  </div>
  <div v-else class="app-shell" :class="{ 'home-layout': route.path === '/home' }">
    <header class="topbar">
      <RouterLink to="/home" class="brand" aria-label="寻迹首页">
        <img class="xunji-brand-symbol" src="/xunji-mark.svg" alt="" width="38" height="38" />
        <span class="brand-name">寻迹</span>
        <span class="brand-subtitle">校园失物招领平台</span>
      </RouterLink>
      <nav class="primary-nav" aria-label="主导航">
        <RouterLink to="/home">首页</RouterLink>
        <RouterLink to="/assistant">AI 寻物</RouterLink>
        <RouterLink to="/found">失物招领</RouterLink>
        <RouterLink to="/lost">寻物启事</RouterLink>
        <RouterLink to="/publish/lost">发布线索</RouterLink>
        <RouterLink to="/me">我的</RouterLink>
      </nav>
      <div class="topbar-actions">
        <CampusPicker />
        <RouterLink v-if="auth.user" class="icon-button notification-button" to="/notifications" aria-label="通知"><AppIcon name="bell" /></RouterLink>
        <details v-if="auth.user" ref="accountMenu" class="account-menu">
          <summary class="account-pill" aria-label="打开个人账户菜单">
            <span class="account-avatar">{{ userInitial }}</span>
            <span class="account-name">{{ auth.user.display_name }}</span>
            <span class="account-chevron" aria-hidden="true">⌄</span>
          </summary>
          <nav aria-label="个人账户">
            <RouterLink to="/me" @click="closeAccountMenu"><strong>个人中心</strong><small>账户概览与设置</small></RouterLink>
            <RouterLink to="/me/items" @click="closeAccountMenu"><strong>我的发布</strong><small>查看、编辑和管理线索</small></RouterLink>
            <RouterLink to="/drafts" @click="closeAccountMenu"><strong>草稿与审核</strong><small>继续编辑或撤回待审内容</small></RouterLink>
            <RouterLink to="/claims" @click="closeAccountMenu"><strong>我的认领</strong><small>跟进核验与交接</small></RouterLink>
            <RouterLink v-if="auth.isManagement" to="/admin/overview" @click="closeAccountMenu"><strong>运营工作台</strong></RouterLink><button type="button" @click="signOut">退出登录</button>
          </nav>
        </details>
        <RouterLink v-else class="login-link" to="/login">登录 / 注册</RouterLink>
      </div>
    </header>
    <AdminNav v-if="route.path.startsWith('/admin/')&&auth.isManagement"/><main id="main-content" tabindex="-1">
      <p v-if="campusSwitching" role="status">正在切换校园…</p>
      <RouterView v-else v-slot="{Component}"><component :is="Component" :key="`${campusRevision}:${auth.user?.id??'guest'}:${route.path}`"/></RouterView>
    </main>
    <footer class="site-footer">
      <RouterLink class="footer-brand" to="/home" aria-label="寻迹首页"><img src="/xunji-mark.svg" alt="寻迹" width="48" height="48" /></RouterLink>
      <nav aria-label="页脚导航"><RouterLink to="/help">使用帮助</RouterLink><RouterLink to="/stations">服务站</RouterLink></nav>
      <RouterLink to="/campus-map">校园地图</RouterLink>
    </footer>
  </div>
</template>
