# Phase 4 REST API

## 安全配置

Domain Pack 管理、审核导出和审核回传使用 `X-Domain-Pack-Token`。服务端只保存令牌的
SHA-256：

```bash
export DI_DOMAIN_PACK_ACCESS_TOKEN_SHA256="$(python - <<'PY'
import hashlib
print(hashlib.sha256(b'replace-with-a-long-random-token').hexdigest())
PY
)"
export DI_ENABLE_DOMAIN_PACK_WRITES=true
```

不配置摘要时，管理和审核读取接口默认拒绝；不打开写入开关时，安装、激活、停用、卸载和
审核回传均拒绝。

## 生命周期接口

- `GET /v1/domain-packs`
- `POST /v1/domain-packs/install`
- `POST /v1/domain-packs/{pack_id}/{version}/activate`
- `POST /v1/domain-packs/{pack_id}/deactivate`
- `DELETE /v1/domain-packs/{pack_id}/{version}`

## 执行和结果

- `POST /v1/domain/apply`
- `GET /v1/domain-results/{domain_result_id}`

默认允许安全回退。回退响应同时返回 `generic_structure`，领域结果中不包含对象或关系断言。

## 审核接口

- `POST /v1/domain-results/{domain_result_id}/review/export`
- `POST /v1/domain-reviews`

审核回传必须携带原导出 ID、领域结果 ID 和来源语义摘要。过期、跨结果或使用未声明标签的
回传会被拒绝。
