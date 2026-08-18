# Phase 8 REST API

## 内置 Domain Pack

以下端点使用 `X-Domain-Pack-Token`：

- `GET /v1/domain-packs/builtin`：列出发行包内置领域包；
- `POST /v1/domain-packs/builtin/{pack_id}/install?activate=false`：安装内置包；
- 既有安装、启用、停用和卸载端点保持不变。

安装仍要求：

- `DI_ENABLE_DOMAIN_PACK_WRITES=true`；
- `DI_DOMAIN_PACK_ACCESS_TOKEN_SHA256`与请求令牌匹配；
- 包通过文件摘要、兼容性和配置的签名门禁。

## 文档族候选检测

以下端点使用独立的 `X-Family-Detection-Token`：

- `POST /v1/family/detect`，请求体：`{"structure_id":"..."}`；
- `GET /v1/family-detections/{detection_id}`。

写入要求：

- `DI_ENABLE_FAMILY_DETECTION_WRITES=true`；
- `DI_FAMILY_DETECTION_ACCESS_TOKEN_SHA256`匹配；
- 活跃Family Profile数量不超过`DI_FAMILY_DETECTION_MAX_PROFILES`。

响应只提供候选、分数、线索证据和血缘。`no_domain_action_executed`固定为`true`，调用者不能把候选响应视为已授权执行。
