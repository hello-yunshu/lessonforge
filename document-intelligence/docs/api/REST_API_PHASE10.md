# Phase 10 REST API：生产资格证据

所有接口使用独立请求头：

```text
X-Production-Qualification-Token: <secret>
```

服务端只保存令牌SHA-256。写入还要求：

```text
DI_ENABLE_PRODUCTION_QUALIFICATION_WRITES=true
```

## 写入接口

- `POST /v1/production/evidence/datasets`
- `POST /v1/production/evidence/parsers`
- `POST /v1/production/evidence/scale`
- `POST /v1/production/evidence/supply-chain`
- `POST /v1/production/evidence/licenses`
- `POST /v1/production/evidence/pilots`
- `POST /v1/production/qualify`

所有写入均产生不可变记录。重复提交相同语义内容幂等返回；相同ID对应不同内容时返回存储冲突。

## 读取接口

- `GET /v1/production/reports/{report_id}`
- `GET /v1/production/inspect`

读取也需要独立令牌。`inspect`只返回计数、策略摘要与是否存在合格报告，不返回敏感原始数据。

## 资格报告语义

```json
{
  "qualified": false,
  "status": "blocked",
  "blocking_reasons": ["..."],
  "automatic_release_authorized": false,
  "human_release_required": true,
  "bounded_auto": false
}
```

即使`qualified=true`，系统也不会自动发布、切换Champion、启用Assist或改变解析路线。
