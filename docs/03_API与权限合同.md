# 03 API 与权限合同

## 1. 协议约定

- 前缀：`/api/v1/`；响应使用 UTF-8 JSON。
- 认证：Django Session；所有非安全方法必须携带 CSRF token。
- 分页：`page`、`page_size`（默认 20，最大 100）。
- 成功：`{"data": ..., "meta": ...}`；失败：`{"error":{"code":"...","message":"...","fields":{...},"request_id":"..."}}`。
- 客户端可用 `Idempotency-Key` 提交发布、认领、审批和交接操作，服务端保存并拒绝重复副作用。

## 2. 核心端点

| 方法 | 路径 | 权限 | 用途 |
|---|---|---|---|
| GET | `/auth/csrf/` | 公开 | 初始化 CSRF cookie |
| POST | `/auth/register/` | 匿名 | 注册普通用户 |
| POST | `/auth/login/` | 匿名 | 登录并轮换会话 |
| POST | `/auth/logout/` | 登录 | 注销并清理会话 |
| GET/PATCH | `/auth/me/` | 登录 | 当前用户与安全可编辑资料 |
| GET | `/items/` | 公开 | 仅返回 `APPROVED` 且可公开的物品 |
| POST | `/items/` | USER+ | 创建本人草稿 |
| GET/PATCH | `/items/{id}/` | 对象权限 | 查看或更新允许字段 |
| POST | `/items/{id}/submit/` | 所有者 | 提交审核 |
| POST | `/admin/reviews/{id}/decision/` | STAFF/ADMIN | 审核通过或驳回 |
| POST | `/matches/runs/` | 登录 | 对本人遗失物发起匹配 |
| GET | `/matches/runs/{id}/` | 所有者/管理 | 运行、配置、索引和候选解释 |
| POST | `/claims/` | 登录 | 针对可认领招领物提交认领 |
| GET | `/claims/{id}/` | 参与者/范围管理 | 认领详情与状态时间线 |
| POST | `/claims/{id}/decision/` | 范围管理 | 补材料/批准/驳回 |
| POST | `/claims/{id}/appointment/` | 参与者/范围管理 | 预约交接 |
| POST | `/claims/{id}/handover/verify/` | 参与者/范围管理 | 验证限次交接码 |
| POST | `/claims/{id}/handover/confirm/` | 双方 | 双方确认后生成返还记录 |
| GET | `/stations/` | 公开 | 服务站及服务状态 |
| GET | `/admin/matching/configs/` | ADMIN | 配置版本列表 |
| POST | `/admin/matching/configs/{id}/publish/` | ADMIN | 原子发布配置并审计 |

登录与注册分别使用 `30/min`、`20/hour` 的限流范围。公网测试进程会统一拒绝文档中已公开的固定演示账号；该限制只由 `DJANGO_PUBLIC_TEST=true` 的公网进程启用，本地答辩进程仍可使用固定演示账号。

## 3. 字段分级

| 级别 | 示例 | 公开 | 本人 | STAFF | ADMIN |
|---|---|---:|---:|---:|---:|
| PUBLIC | 类别、模糊地点、日期、公开描述 | ✓ | ✓ | ✓ | ✓ |
| OWNER | 草稿、审核意见、匹配运行 | — | ✓ | 范围内 | ✓ |
| SENSITIVE | 候选/拾获地点、精确坐标、联系方式、原图 EXIF | — | ✓ | 按需且留痕 | 按需且留痕 |
| SECRET | 私密特征答案、交接码摘要 | — | 最小化 | 审批流程最小化 | 不直接返回 |

私密答案仅用于服务端验证和证据比对，不在任何序列化器中原样返回。管理员也不得从通用列表接口批量获取敏感字段。

物品写入有两种互斥的受保护地点来源：演示/结构化校区通过 `location_candidate_ids` 提交地点 ID，真实地图通过 `location_candidate_points` 提交 GCJ-02 坐标、显示标签与顺序。遗失线索最多 5 个且数组顺序即可能性顺序，招领线索最多 1 个。授权详情分别返回 `location_candidates` 或 `coordinate_candidates`；匿名或非授权访问会整体移除候选字段、顶层兼容坐标及位置细节。

## 4. 越权策略

- 未登录返回 401；已登录但无角色能力返回 403。
- 对可枚举的他人私有对象统一返回 404，避免确认对象存在性。
- STAFF 的管理查询必须强制过滤其有效站点成员关系；不得接受前端传入的 `station_id` 作为唯一授权依据。
- 状态迁移使用服务层白名单，禁止通过通用 PATCH 任意修改状态。
