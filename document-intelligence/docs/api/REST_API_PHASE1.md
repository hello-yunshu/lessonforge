# Phase 1 REST API

## `GET /healthz`

返回服务版本和核心 Schema 版本。

## `GET /v1/parsers`

返回全部已注册解析器的：

- 是否启用；
- 是否可用；
- 固定版本；
- 产物摘要；
- 不可用原因；
- 能力列表。

## `POST /v1/parse`

表单字段：

- `file`：PDF、PNG、JPEG 或 WebP；
- `parser_id`：默认 `auto`；
- `domain_pack`：可空；
- `include_document`：默认 `true`。

Phase 1 的 `auto` 对 PDF 首选 Native PDF。外部解析器未满足版本、地址、摘要门禁时不会进入候选列表。

## `GET /v1/runs/{run_id}`

读取已原子提交的成功解析结果。失败记录单独保存在 `var/runs/*.failed.json`，不会伪装成成功运行。
