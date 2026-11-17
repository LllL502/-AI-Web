<script setup lang="ts">
import { RouterLink } from 'vue-router'
import AppIcon from '../../components/AppIcon.vue'
import AMapCampus from '../../components/AMapCampus.vue'

</script>

<template>
  <section class="home-hero">
    <div class="hero-copy">
      <p class="eyebrow"><AppIcon name="spark" /> AI 辅助 · 人工核验</p>
      <h1>让每一件遗失，<br /><em>都有回来的方向。</em></h1>
      <p>基于 TF-IDF、余弦相似度与缺失感知六因子融合，把分散的校园线索整理成可解释、可核查的候选，而不是替你草率认定归属。</p>
      <div class="hero-actions">
        <RouterLink class="button button-brand" to="/publish/lost"><AppIcon name="plus" />我丢了物品</RouterLink>
        <RouterLink class="button button-ghost" to="/publish/found"><AppIcon name="box" />我捡到物品</RouterLink>
      </div>
      <dl class="trust-strip">
        <div><dt>六因子</dt><dd>公开证据解释</dd></div>
        <div><dt>双状态</dt><dd>审核与业务分离</dd></div>
        <div><dt>限次码</dt><dd>线下安全交接</dd></div>
      </dl>
    </div>
    <div class="hero-scene">
      <AMapCampus compact />
      <p class="scene-caption"><RouterLink to="/campus-map">进入校园地图，搜索并核对真实地点 →</RouterLink></p>
    </div>
  </section>
  <section class="home-section">
    <div class="section-heading"><div><p class="eyebrow">CLEAR WORKFLOW</p><h2>从线索到找回，每一步都可追溯</h2></div><RouterLink to="/help">查看完整流程 <AppIcon name="arrow" /></RouterLink></div>
    <div class="process-grid">
      <article><span>01</span><h3>发布与隐私分层</h3><p>公开描述用于检索，精确地点和核验答案只在授权流程内使用。</p></article>
      <article><span>02</span><h3>审核与智能匹配</h3><p>审核通过后进入索引，用同一 TF-IDF 空间和六因子评分生成候选。</p></article>
      <article><span>03</span><h3>举证与安全交接</h3><p>站点协调员核验举证，唯一保留、限次交接码与双方确认完成归还。</p></article>
    </div>
  </section>
</template>

<style scoped>
.home-hero { display: grid; grid-template-columns: .84fr 1.16fr; gap: 56px; align-items: center; width: min(var(--ct-max), calc(100% - 48px)); min-height: calc(100vh - 72px); margin: auto; padding: 70px 0; }
.hero-copy h1 { margin: 18px 0 24px; font-family: Georgia, "Songti SC", serif; font-size: clamp(48px, 6vw, 82px); line-height: 1.02; letter-spacing: -.055em; }
.hero-copy h1 em { color: var(--ct-brand-strong); font-style: normal; }
.hero-copy > p:not(.eyebrow) { max-width: 570px; color: var(--ct-text-muted); font-size: 17px; line-height: 1.9; }
.hero-actions { display: flex; gap: 12px; margin: 32px 0; }
.trust-strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; overflow: hidden; margin: 42px 0 0; border: 1px solid var(--ct-border); border-radius: 14px; background: var(--ct-border); }
.trust-strip div { padding: 16px; background: var(--ct-bg-soft); }
.trust-strip dt { color: var(--ct-brand); font-weight: 800; }
.trust-strip dd { margin: 5px 0 0; color: var(--ct-text-muted); font-size: 11px; }
.hero-scene { position: relative; }
.scene-caption { display: flex; align-items: center; gap: 12px; margin: 14px 4px 0; color: var(--ct-text-muted); font-size: 12px; }
.home-section { width: min(var(--ct-max), calc(100% - 48px)); margin: 20px auto 0; padding: 70px 0; }
.section-heading { display: flex; justify-content: space-between; align-items: end; gap: 24px; }
.section-heading h2 { margin: 10px 0 0; font-size: clamp(28px, 4vw, 44px); }
.section-heading > a { display: inline-flex; align-items: center; gap: 7px; color: var(--ct-brand); }
.process-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-top: 30px; }
.process-grid article { padding: 26px; border: 1px solid var(--ct-border); border-radius: var(--ct-radius-md); background: var(--ct-surface-glass); }
.process-grid span { color: var(--ct-brand); font-family: Georgia, serif; font-size: 30px; }
.process-grid h3 { margin: 22px 0 9px; }
.process-grid p { margin: 0; color: var(--ct-text-muted); line-height: 1.7; }
@media (max-width: 960px) { .home-hero { grid-template-columns: 1fr; padding-top: 46px; } .process-grid { grid-template-columns: 1fr; } }
@media (max-width: 620px) { .home-hero, .home-section { width: calc(100% - 28px); } .hero-copy h1 { font-size: 46px; } .trust-strip { grid-template-columns: 1fr; } .section-heading { align-items: start; flex-direction: column; } }
</style>
