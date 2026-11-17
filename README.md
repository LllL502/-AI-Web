# 寻迹 · 校园多模态智能寻物助手

**森林冰火人｜西安交通大学｜冷绮文、段宇桐**

把一句描述、一张照片整理成可核对的寻物线索，并衔接发布、认领与实物交接。

- 参赛项目：第九届传智杯 AI WEB 网页开发挑战赛（届次由团队确认）。
- 代码仓库：https://github.com/LllL502/-AI-Web
- 当前材料版本：2026-11-17 本地验收版本。正式域名与服务器验收结果尚未提供，不将本地地址写成上线地址。
- 技术文档：[PDF](docs/submission/寻迹_技术文档.pdf)；[提交状态](docs/submission/提交检查表.md)。

## 项目介绍

寻迹面向校园失物招领中描述零散、检索困难、跨校区混淆和交接风险等问题。小寻通过对话整理物品、外观、地点与时间；图片观察经用户核对后参与文本检索。候选来自当前校区仍公开且开放的真实数据库记录，提供评分依据，随后进入认领核验和双方交接。

小寻可在明确确认后调用发布、认领、预约、补充材料和交接等受限业务接口；所有动作仍由服务器检查角色、归属、状态与幂等键。AI不能自行认定物品归属，也不能替另一方确认实物交接。

## 核心功能

- 失物/招领发布、最多3张实拍图片、安全重编码、审核、编辑和关闭。
- 学校与校区选择、公开广场、地图与服务站、收藏、站内会话。
- 小寻连续对话、原文证据约束、日期与钟点分别处理、明确确认后办理业务。
- 图片理解 → 人工核对 → 文本向量召回 → 六因子重排及候选拒绝。
- 私密核验证据、认领状态机、直接或服务站交接、双方确认与审计。
- 新线索关键词订阅、审核/认领/消息提醒、偏好开关和事件去重。
- 管理端参数版本复制、草稿编辑、发布、历史重启用和四项AI服务状态检查。
- 可爱Q版全身3D小寻、20秒动作轮换和本地动态童声；降低动态效果设置有降级处理。

演示校区与真实校区分开。参考照片明确标注，不冒充某条失物的现场实拍。没有照片的用户记录不自动填入虚构图片。

## 技术架构

| 层次 | 实现 |
|---|---|
| 前端 | Vue 3、TypeScript、Pinia、Vue Router、Vite、Three.js、ECharts |
| 后端 | Python 3.12、Django 5.2、Django REST Framework、MySQL 8.4 |
| 对话/图片 | Ollama + Qwen3-VL 4B Instruct，OpenAI-compatible接口 |
| 语义召回 | Qwen3-Embedding 0.6B、持久化向量、余弦相似度 |
| 可解释排序 | TF-IDF或语义分数 + 类别/地点/时间/颜色/品牌六因子 |
| 语音 | Qwen3-TTS 1.7B VoiceDesign，本地CPU预加载、需要时占用GPU |
| 部署 | Docker Compose、Caddy HTTPS、Waitress；生产环境另行验收 |

这是“图片转文字后检索”，不是图文共享向量空间中的直接图片相似检索。匹配分是排序证据，不能当成物品归属概率。

## 获取源码与依赖

```bash
git clone https://github.com/LllL502/-AI-Web.git
cd -- -AI-Web
```

锁定依赖：`backend/requirements.lock`、`frontend/package-lock.json`；可选童声环境见 `scripts/requirements.voice.lock`。下载的数据库运行包、模型权重、虚拟环境、用户图片与真实环境变量不进入Git仓库。

## 本地运行：Windows完整演示

前置：Python 3.12、Node.js 22.12+或24、Git；完整本地AI建议具备CUDA显卡。本次本地验证使用RTX 4060 Laptop 8GB与32GB内存，不将其视为已完成的多人容量测试。

1. 下载MySQL 8.4 Windows ZIP放入 `tools/`，目录与脚本约定见 [环境与复现](docs/submission/环境与复现.md)。
2. 执行 `scripts/setup.cmd` 创建本地依赖、数据库和确定性演示数据。该脚本仅供本地演示，会配置本地数据库账户，已有数据库先备份。
3. 按 [本地AI配置](docs/submission/环境与复现.md) 安装Ollama和模型，将 `backend/.env.local-ai.example` 的AI配置合并到本机 `.env`。
4. 可选安装童声依赖及权重；未安装童声时文字交互仍可使用，但健康检查会明确报告语音未就绪。
5. 启动并检查：

```powershell
scripts\start.cmd
scripts\health.cmd
```

网页：`http://127.0.0.1:5173/`；停止：`scripts/stop.cmd`。启动脚本使用完整入口，不能只启动网页而遗漏模型。童声首次启动先预加载CPU权重，准备中不会报告为已就绪。

## 通用开发环境

已有MySQL时，可使用标准依赖安装流程。先复制 `backend/.env.example` 为 `backend/.env`，填写自己创建的数据库账户和随机密钥：

```bash
python -m venv backend/.venv
# 激活对应系统的虚拟环境后执行
python -m pip install -r backend/requirements.lock
cd backend
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 127.0.0.1:8000
```

另开终端：

```bash
cd frontend
npm ci
npm run dev
```

模板的 `development_stub` 仅用于明确标注的开发模拟，不能据此宣称已经接通真实模型。真实推理需要另外配置和启动服务。

演示账户由 `seed_demo` 创建，账号信息见 `docs/submission/环境与复现.md`。仅可用于隔离演示环境；公开部署前必须更换密码并限定演示账号权限。

## 测试与复现

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
python manage.py check
python manage.py makemigrations --check --dry-run
cd ..\frontend
npm test
npm run build
npx playwright test tests/e2e/ten-fixes.spec.ts
```

后端测试需要项目MySQL及测试库权限。浏览器测试使用Edge，真实AI场景需启动本地模型并显式设置 `CAMPUSTRACE_REAL_LOCAL_AI=1`，不能把模拟接口检查当作真实推理效果。

2026-11-17已留存证据：后端完整回归233项通过，最终相关专项16项通过；前端74项通过，正式构建通过；80个页面与视口组合检查无页面运行异常或非预期请求失败；参数管理的2项浏览器交互用例通过，写接口使用模拟响应。证据与边界见 `evidence/verification-summary.json`。

固定v2合成评测包含24条查询（开发/验证各12条，各8条正例和4条无答案）。候选过滤后的开发与验证正例首位命中均为8/8，无答案错误返回均为0/4；样本很小且非独立盲测，不能宣称真实识别率、找回率或通用准确率100%。数据、人工复核与原报告在 `data/benchmark/` 和 `evidence/benchmark/`。

## 生产部署

使用 `deploy/.env.production.example`、`docker-compose.prod.yml` 与 [部署文档](docs/13_正式生产部署.md)。必须配置正式域名、随机密钥、数据库密码和HTTPS。媒体请求经过后端授权，不能把整个媒体目录直接暴露给静态服务器。

模型推理必须运行在上线后可用的服务端。电脑上的 `127.0.0.1` 不能直接代表云服务器模型；当前视觉/向量请求限定本机HTTP。若使用容器，必须明确推理服务与后端共享回环网络的方案，或改用经过验证的适配方式。当前Compose模板不自动启动GPU模型或童声环境，不宣称一键部署后即可获得全部AI能力。

备份：`sh deploy/backup.sh`；隔离恢复演练：`sh deploy/verify-backup.sh 备份目录`。本地已完成真实数据库与媒体恢复演练，服务器Docker、域名与HTTPS仍须上线后验收。

## 团队与开发记录

| 项目 | 正式信息 |
|---|---|
| 团队 | 森林冰火人 |
| 学校 | 西安交通大学 |
| 成员 | 冷绮文、段宇桐 |

个人分工、指导教师与参赛编号尚未提供，本仓库不据此推断或虚构个人贡献。

历史版本此前保存在本地，未逐次同步到远程仓库。现已保留全部已有Git提交，并补充10月9日前端、10月15日前后端框架、11月15日前端及两份本地源码快照，附原始交付记录和文件校验清单。详见[历史版本与真实开发过程](docs/submission/历史版本归档说明.md)。本次归档使用实际提交时间，原版本时间依据单独记录，不倒填日期，也不补造早期逐次提交。

## 目录与素材

```text
backend/     API、业务权限、模型适配、数据库迁移与测试
frontend/    网站、3D小寻与前端测试
scripts/     安装、启动、模型下载、检查与材料生成
deploy/      生产模板、HTTPS、备份与恢复脚本
data/        确定性演示素材、学校来源与固定评测（无运行数据库）
docs/        当前说明与按日期保留的阶段记录
evidence/    精选验证汇总、固定评测与素材来源
```

素材归属、来源与再分发范围见 `THIRD_PARTY_NOTICES.md`。团队自有代码当前未额外授予开源许可；公开托管不等于放弃著作权。第三方代码与模型继续遵守各自许可。
