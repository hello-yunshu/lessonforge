# Phase 1 错误类型库

## P0：不可接受、必须阻断

| 代码 | 含义 | 当前防线 |
|---|---|---|
| `PARSER_DIGEST_MISMATCH` | 外部服务或模型摘要与固定值不一致 | 健康检查及解析结果双重比对 |
| `OUTPUT_SCHEMA_INVALID` | 外部输出不能通过统一 Schema | Pydantic 严格校验 |
| `OUTPUT_EVIDENCE_MISSING` | 元素或关系缺少证据 | 图一致性校验 |
| `STANDARD_RESULT_POLLUTION` | 普通解析修改标准结果 | 标准目录快照和独立事务路径 |

## P1：关键解析错误

| 代码 | 含义 | 当前防线 |
|---|---|---|
| `INPUT_CORRUPT` | 文件为空、超限或 PDF 损坏 | 导入策略和 PyMuPDF 异常转换 |
| `PARSER_VERSION_MISMATCH` | 远端版本与固定版本不同 | 健康检查及结果校验 |
| `EXTERNAL_RAW_OUTPUT_INVALID` | 网关输出不符合协议 | HTTP 网关合约测试 |

## P2：可恢复或需要降级

| 代码 | 含义 | 当前行为 |
|---|---|---|
| `INPUT_UNSUPPORTED` | 输入格式尚无可用解析器 | 明确拒绝，不尝试猜测 |
| `PARSER_UNAVAILABLE` | 服务关闭、地址缺失或健康失败 | 记录失败并尝试下一候选 |
| `PARSER_TIMEOUT` | 外部解析器超时 | 记录并降级 |
| `EMPTY_NATIVE_TEXT` | 扫描 PDF 没有原生文字层 | 自动尝试后续 OCR 候选；无候选则返回明确警告 |

配置真值位于 `configs/error_taxonomy.yaml`。
