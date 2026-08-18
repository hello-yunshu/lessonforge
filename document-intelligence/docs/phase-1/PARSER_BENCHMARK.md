# Phase 1 多解析器横向基线

## Native PDF 实测

| 夹具 | 类型 | 页数 | 元素 | 文本 | 图片 | 中位耗时(ms) | 可复现 | 警告 |
|---|---|---:|---:|---:|---:|---:|---|---|
| native_text.pdf | native-text-report | 1 | 15 | 15 | 0 | 6.17 | 是 | - |
| scanned_image.pdf | image-only-scan | 1 | 1 | 0 | 1 | 85.717 | 是 | EMPTY_NATIVE_TEXT |
| mixed_layout.pdf | mixed-text-image | 2 | 6 | 5 | 1 | 8.004 | 是 | - |

## 解析器可用性

| 解析器 | 启用 | 可用 | 固定版本 | 摘要 | 原因 |
|---|---|---|---|---|---|
| mineru-benchmark | False | False | 3.3 | - | disabled by configuration |
| native-pdf | True | True | 5.9.0 | b171f3401bb9f0d06dd483cd32bb752c0992e99c305a123b8117ffa7a9fe17fa | - |
| opendoc | False | False | 0.1.5 | - | disabled by configuration |
| paddle | False | False | 3.7.0 | - | disabled by configuration |

## 结论

- Native PDF 解析已完成真实运行、重复回放和语义摘要一致性验证。
- PaddleOCR、OpenDoc、MinerU 采用 fail-closed 网关：未固定服务地址和 SHA-256 时不可用。
- 当前离线环境未安装三套重型模型，因此不虚构其准确率；网关身份、版本、摘要和统一输出合约已通过测试。
- 外部模型进入生产前必须在相同黄金集上补齐真实准确率、资源和许可证报告。
