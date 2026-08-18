# Phase 6 REST API

所有Assist端点使用`X-Rill-Assist-Token`，服务端仅保存令牌SHA-256。写入还要求`DI_ENABLE_RILL_ASSIST_WRITES=true`，执行及解析器熔断还要求`DI_ENABLE_RILL_ASSIST_EXECUTION=true`。

- `POST /v1/rill/assist/attest`：提交专家证据证明；
- `POST /v1/rill/assist/qualify`：生成资格报告；
- `GET /v1/rill/assist/qualifications/{report_id}`：读取资格；
- `POST /v1/rill/assist/activate`：人工批准Tier 1动作和限流；
- `POST /v1/rill/assist/revoke`：紧急撤销激活；
- `POST /v1/rill/assist/execute`：对一个既有Shadow评估执行附加动作；
- `POST /v1/rill/assist/parsers/suspend`：绑定漂移告警暂停非native解析器；
- `POST /v1/rill/assist/parsers/resume`：人工恢复解析器；
- `GET /v1/rill/assist/inspect`：查看资格、激活、执行、队列和熔断摘要。

执行端点不会返回或创建替换既有结果的对象。安全阻断以不可变执行记录返回；访问、资格和存储损坏仍使用结构化错误响应。


## Runtime产物证明

资格生成与激活除要求宿主固定Runtime、模型包和Handler的SHA-256外，还要求真实Runtime的`inspect`响应包含：

```json
{
  "artifactDigests": {
    "runtimeSha256": "<64位小写十六进制>",
    "modelSha256": "<64位小写十六进制>",
    "handlerSha256": "<64位小写十六进制>"
  }
}
```

任一字段缺失或与宿主固定值不一致，资格报告加入`RUNTIME_ARTIFACT_ATTESTATION_REQUIRED`并保持未通过。
