# 寻迹｜第九届前端优化交接

交接编号：xunji-frontend-20261115-v1。请完整保留此文件、handoff.json 和 baseline-sha256.json，返还时一并发送。

## 立即开始（无需后端）

安装 Node.js 22.12+（建议22 LTS或24），解压后在 frontend 目录执行：

```powershell
npm ci
npm run dev:design
```

打开 http://127.0.0.1:5173/home 。进入 /assistant 可设计照片上传、确认卡和候选结果；样例用户自动登录。此模式仅用于视觉交互预览，数据和识别结果都是固定样例，不调用AI，不实际提交业务操作。其他业务页面需要真实后端，不是全站完整离线业务模拟。

停止用 Ctrl+C。5173已占用时请先关闭对应开发服务。首次安装依赖需要网络，不需要本地模型、数据库或任何密钥。

## 真实接口模式

`npm run dev` 默认代理到本机8000端口；没有后端时不能登录或办理业务。仅在负责人提供经授权的后端及相应Host/CSRF配置后联调，代理地址通过 CAMPUS_TRACE_API_TARGET 环境变量设置。不要自行开放负责人电脑或连接生产数据。包内没有后端与真实凭据。

## 优化重点

目标是成熟、有吸引力的校园寻物产品。允许重新设计页面、组件、字体、配色、响应式和必要动效。减少无意义的小字提醒，保留可见的错误、人工确认、演示素材标记和必要的操作反馈；不要倾斜主卡片，不伪造使用人数、成功率、物品或校园数据。

优先改 src/views、src/components、src/styles、public；确保360/390px手机和1440px桌面可用，支持键盘操作与低动效偏好。当前入口与交互以源码为准，reference中部分历史说明不一定反映最新文案。

## 整合约定

- 保持现有路由地址、接口路径/字段/枚举。src/api/client.ts 的Cookie、CSRF、X-Campus-ID，登录守卫、角色权限与校园隔离不要为方便预览而删除。
- 修改请求字段或新增接口时，单独列出需求，由负责人配套后端；不要把Mock替换成正式接口实现。
- 设计模式只在此包的 handoff-preview.ts 中，通过 dev:design 显式启用。它不是需要迁回正式工程的业务代码。
- 新增依赖请同时提交 package.json / package-lock.json。不要提交 .env、node_modules、dist、浏览器登录状态、上传的私人图片、密钥或模型。

## 自检与返还

```powershell
npm test
npm run build
```

前端基线41项单测，类型检查和构建通过。文案或结构有意变更时更新对应测试，不能直接删掉功能测试。Playwright需另装浏览器；现有真实AI端到端测试需要完整后端和模型，纯设计模式不等价于真实验收。

请返还一个压缩包，包含完整 frontend 源码、原始 handoff.json、baseline-sha256.json，以及 CHANGELOG.md。变更说明请列出：改了哪些页面、新增依赖、接口需求、自测结果、桌面/手机截图、未完成项与新增素材来源授权。不要只返还dist。

负责人保存了原始源码快照与交接时文件哈希。返还后按“原始工程—交付给你的版本—你的返还版本—负责人当前版本”比较，再逐项合并，避免覆盖双方新增修改。保留相对路径和交接编号，即使没有使用Git也能对比；使用Git则请保留真实提交或补充git diff。

此包为方便独立预览，仅额外改动了 vite.config.ts 的插件注册及 package.json 的 dev:design 命令；新增 handoff-preview.ts、scripts/design-preview.mjs 和 public/design-assets。整合时这些预览改动单独处理。
