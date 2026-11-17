<script setup lang="ts">
import { computed, ref } from 'vue'
import { campusRevision, campusSwitching } from './stores/campus'
import CampusPicker from './components/CampusPicker.vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import AppIcon from './components/AppIcon.vue'
import CampusSketch from './components/CampusSketch.vue'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const isSystemPage = computed(() => route.meta.layout === 'system')
const accountMenu = ref<HTMLDetailsElement | null>(null)

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
    <RouterView v-if="!campusSwitching" :key="campusRevision" />
  </div>
  <div v-else class="app-shell" :class="{ 'home-layout': route.path === '/home' }">
    <header class="topbar">
      <RouterLink to="/home" class="brand" aria-label="拾光首页">
        <span class="brand-mark"><AppIcon name="campus" /></span>
        <span><strong>校园失物招领</strong><small>拾光 · CampusTrace</small></span>
      </RouterLink>
      <nav class="primary-nav" aria-label="主导航">
        <RouterLink to="/home">首页</RouterLink>
        <RouterLink to="/lost">寻物启事</RouterLink>
        <RouterLink to="/found">失物招领</RouterLink>
        <RouterLink to="/campus-map">校园地图</RouterLink>
        <RouterLink to="/matches">智能匹配</RouterLink>
      </nav>
      <div class="topbar-actions">
        <CampusPicker />
        <RouterLink class="icon-button" to="/search" aria-label="搜索"><AppIcon name="search" /></RouterLink>
        <RouterLink v-if="auth.user" class="icon-button" to="/notifications" aria-label="通知"><AppIcon name="bell" /></RouterLink>
        <RouterLink v-if="!auth.user" class="button button-ghost" to="/login">登录</RouterLink>
        <details v-else ref="accountMenu" class="account-menu">
          <summary class="account-pill" aria-label="打开个人账户菜单">
            <AppIcon name="user" /><span class="account-name">{{ auth.user.display_name }}</span><span aria-hidden="true">⌄</span>
          </summary>
          <nav aria-label="个人账户">
            <RouterLink to="/me" @click="closeAccountMenu"><strong>个人中心</strong><small>账户概览与设置</small></RouterLink>
            <RouterLink to="/me/items" @click="closeAccountMenu"><strong>我的发布</strong><small>查看、编辑和管理线索</small></RouterLink>
            <RouterLink to="/drafts" @click="closeAccountMenu"><strong>草稿与审核</strong><small>继续编辑或撤回待审内容</small></RouterLink>
            <RouterLink to="/claims" @click="closeAccountMenu"><strong>我的认领</strong><small>跟进核验与交接</small></RouterLink>
            <button type="button" @click="signOut">退出登录</button>
          </nav>
        </details>
        <RouterLink class="button button-brand" to="/publish/lost"><AppIcon name="plus" />发布线索</RouterLink>
      </div>
    </header>
    <main id="main-content" tabindex="-1">
      <p v-if="campusSwitching" role="status">正在切换校园…</p>
      <RouterView v-else :key="campusRevision" />
    </main>
    <aside class="campus-ribbon"><CampusSketch class="ribbon-campus" /><div><p>拾起的不只是物品，更是一份校园温度。</p><small>A WARMER CAMPUS TOGETHER</small></div><RouterLink to="/publish/found">让善意有处安放 ↗</RouterLink></aside>
    <footer class="site-footer">
      <div><strong>拾光 · CampusTrace</strong><p>让每一件遗失，都有回来的方向。</p></div>
      <nav aria-label="页脚导航"><RouterLink to="/help">使用帮助</RouterLink><RouterLink to="/stations">服务站</RouterLink><RouterLink to="/stories">找回故事</RouterLink></nav>
      <p class="footer-note"><AppIcon name="shield" />隐私分级 · 人工核验 · 全程留痕</p>
    </footer>
  </div>
</template>
