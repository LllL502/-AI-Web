<script setup lang="ts">
import { computed, onMounted } from 'vue'
import CampusPicker from './components/CampusPicker.vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import AppIcon from './components/AppIcon.vue'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const isSystemPage = computed(() => route.meta.layout === 'system')

onMounted(() => auth.bootstrap())

async function signOut() {
  await auth.logout()
  await router.push('/home')
}
</script>

<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a>
  <div v-if="isSystemPage" class="system-layout">
    <RouterView />
  </div>
  <div v-else class="app-shell">
    <header class="topbar">
      <RouterLink to="/home" class="brand" aria-label="拾光首页">
        <span class="brand-mark"><AppIcon name="spark" /></span>
        <span><strong>拾光</strong><small>CampusTrace</small></span>
      </RouterLink>
      <nav class="primary-nav" aria-label="主导航">
        <RouterLink to="/lost">遗失广场</RouterLink>
        <RouterLink to="/found">招领广场</RouterLink>
        <RouterLink to="/campus-map">校园地图</RouterLink>
        <RouterLink to="/matches">智能匹配</RouterLink>
      </nav>
      <div class="topbar-actions">
        <CampusPicker />
        <RouterLink class="icon-button" to="/search" aria-label="搜索"><AppIcon name="search" /></RouterLink>
        <RouterLink v-if="auth.user" class="icon-button" to="/notifications" aria-label="通知"><AppIcon name="bell" /></RouterLink>
        <RouterLink v-if="!auth.user" class="button button-ghost" to="/login">登录</RouterLink>
        <button v-else class="account-pill" type="button" @click="signOut">
          <AppIcon name="user" />{{ auth.user.display_name }}<span>退出</span>
        </button>
        <RouterLink class="button button-brand" to="/publish/lost"><AppIcon name="plus" />发布线索</RouterLink>
      </div>
    </header>
    <main id="main-content" tabindex="-1">
      <RouterView />
    </main>
    <footer class="site-footer">
      <div><strong>拾光 · CampusTrace</strong><p>让每一件遗失，都有回来的方向。</p></div>
      <nav aria-label="页脚导航"><RouterLink to="/help">使用帮助</RouterLink><RouterLink to="/stations">服务站</RouterLink><RouterLink to="/stories">找回故事</RouterLink></nav>
      <p class="footer-note"><AppIcon name="shield" />隐私分级 · 人工核验 · 全程留痕</p>
    </footer>
  </div>
</template>
