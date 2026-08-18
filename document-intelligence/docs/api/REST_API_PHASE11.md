# Phase 11 REST API

## 1. 权限

活动接口使用：

```text
X-DI-Access-Token
```

服务端仅保存：

```text
DI_QUALIFICATION_CAMPAIGN_ACCESS_TOKEN_SHA256
```

写入还要求：

```text
DI_ENABLE_QUALIFICATION_CAMPAIGN_WRITES=true
```

Bundle恢复会同时写入生产资格证据，因此额外要求：

```text
DI_ENABLE_PRODUCTION_QUALIFICATION_WRITES=true
X-DI-Production-Token
```

活动权限与生产资格权限不能相互替代。

## 2. 活动管理

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/v1/qualification-campaigns` | 创建不可变活动Manifest |
| GET | `/v1/qualification-campaigns/inspect` | 检查活动数量和安全状态 |
| GET | `/v1/qualification-campaigns/{campaign_id}` | 重放并读取活动快照 |
| POST | `/v1/qualification-campaigns/{campaign_id}/start` | 启动活动 |
| POST | `/v1/qualification-campaigns/{campaign_id}/pause` | 暂停活动 |
| POST | `/v1/qualification-campaigns/{campaign_id}/resume` | 恢复活动 |
| POST | `/v1/qualification-campaigns/{campaign_id}/cancel` | 取消活动 |

活动只有在`external_data_authorized=true`时才能启动。

## 3. 步骤执行

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `.../steps/{step_id}/claim` | 领取就绪步骤并获得租约 |
| POST | `.../steps/{step_id}/heartbeat` | 在上限内续租 |
| POST | `.../steps/{step_id}/checkpoint` | 保存进度、游标摘要和指标 |
| POST | `.../steps/{step_id}/evidence` | 链接已验证生产资格证据 |
| POST | `.../steps/{step_id}/complete` | 完成已满足证据要求的步骤 |
| POST | `.../steps/{step_id}/fail` | 标记步骤失败 |
| POST | `.../steps/{step_id}/retry` | 将失败步骤恢复为待处理 |

步骤依赖未完成、租约不匹配、租约过期、证据类型错误、证据上下文冲突或重复证据时，
请求失败关闭。

综合资格步骤不能通过`claim`领取，只能由`finalize`执行。

## 4. 综合资格

```text
POST /v1/qualification-campaigns/{campaign_id}/finalize
```

该操作从已链接证据构造生产资格请求，并由Phase 10资格服务按当前策略重新评估。
返回的`production_qualified`不等于发布授权；以下字段永久为false：

```json
{
  "automatic_release_authorized": false,
  "bounded_auto": false
}
```

## 5. 密封包

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/v1/qualification-campaigns/{campaign_id}/bundle` | 生成或验证确定性密封包 |
| POST | `/v1/qualification-campaigns/bundles/import` | 验证并恢复活动及证据 |

导出响应只返回Bundle Manifest，不返回服务器绝对路径。导入限制由
`DI_QUALIFICATION_CAMPAIGN_MAX_BUNDLE_BYTES`控制。

## 6. 错误语义

- `QUALIFICATION_CAMPAIGN_ACCESS_DENIED`：令牌未配置或不匹配；
- `QUALIFICATION_CAMPAIGN_WRITE_DISABLED`：写入开关关闭；
- `QUALIFICATION_CAMPAIGN_BLOCKED`：状态、依赖、租约或证据门禁失败；
- `QUALIFICATION_CAMPAIGN_STORE_CORRUPT`：记录、摘要、事件链或Bundle损坏。
