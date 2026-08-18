# Phase 5 REST API

所有Rill接口均要求 `X-Rill-Token`，服务端只保存令牌SHA-256。写接口还要求 `DI_ENABLE_RILL_SHADOW_WRITES=true`。

- `POST /v1/rill/shadow/evaluate`：生成并保存不可执行的Shadow建议。
- `GET /v1/rill/shadow/evaluations/{evaluation_id}`：读取已验证建议。
- `POST /v1/rill/shadow/feedback`：提交一次性最终人工反馈。
- `GET /v1/rill/shadow/replay`：比较Rill、静态策略和人工最终动作。
- `GET /v1/rill/shadow/inspect`：读取Runtime、漂移和回放摘要。
- `POST /v1/rill/shadow/snapshot`：保存Runtime与宿主漂移状态。
- `POST /v1/rill/shadow/reset`：先快照再按generation重置。

所有evaluation均返回：

```json
{"shadow_only": true, "no_action_executed": true}
```

这些接口不存在解析器切换、标准结果接受、模型发布或规则修改操作。
