# 统一解析器网关协议 v1

Phase 1 不让核心服务直接绑定 PaddleOCR、OpenDoc 或 MinerU 的不稳定私有输出。每个外部引擎由一个很薄的网关封装，并遵守以下协议。

## 健康检查

`GET /healthz`

```json
{
  "parser_id": "paddle",
  "version": "3.7.0",
  "artifact_sha256": "64位小写十六进制摘要"
}
```

核心服务会逐项比对：

- `parser_id`；
- 固定版本；
- 容器镜像或模型产物 SHA-256。

任一项不一致均 fail closed。

## 解析

`POST /v1/parse`，`multipart/form-data`：

- `file`：原始 PDF 或图片；
- `input_sha256`：核心侧输入摘要；
- `domain_pack`：可空。

响应：

```json
{
  "gateway": {
    "parser_id": "paddle",
    "version": "3.7.0",
    "artifact_sha256": "..."
  },
  "result": {
    "document": "符合 ParsedDocument Schema",
    "run": "符合 ParseRun Schema",
    "raw_output": "可选"
  }
}
```

## 安全约束

1. 网关不得回写标准结果库。
2. 网关必须保留供应商原始输出引用。
3. 结果中的输入 SHA-256 必须与请求一致。
4. 核心服务再次执行 Pydantic Schema 和证据图校验。
5. 供应商升级必须产生新的版本和摘要，不得覆盖旧产物。
