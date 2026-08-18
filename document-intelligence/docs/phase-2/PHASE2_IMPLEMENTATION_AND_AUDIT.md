---
title: Phase 2 标准文档匹配实施与冻结审计
project: document-intelligence
version: 0.2.0
status: engineering-complete-production-qualification-pending
date: 2026-08-02
---

# Phase 2 标准文档匹配实施与冻结审计

## 1. 阶段目标

Phase 2实现已审核标准文档的不可变入库、全页和局部截图匹配，以及只有证据充分时才允许调用标准结果的安全门禁。核心系统保持领域中立，领域知识继续由Domain Pack承载。

## 2. 已完成能力

- 标准文档显式审核入库；
- 原文件、标准结构、页面图像、缩略图和局部特征版本化；
- 页面图像指纹、dHash、文本n-gram和布局摘要；
- ORB特征和RANSAC几何验证；
- 全页、局部裁剪、未知页和重复页判断；
- 候选排序、总分、候选间隔和几何证据联合门禁；
- 标准清单、页面索引和特征文件完整性验证；
- 匹配器、指纹流水线、标准索引和阈值的可复现元数据；
- 标准库访问令牌、默认拒绝和写入开关；
- Rill Observe匹配信号，保持Shadow；
- API、CLI、Schema、Docker、CI和发布脚本。

## 3. 标准库安全模型

标准文档注册必须满足：

1. 来源于成功且完整性可验证的解析运行；
2. 原始输入已按SHA-256留存；
3. 调用方提供审核人、审核说明和 `approved=true`；
4. `DI_ENABLE_STANDARD_WRITES=true`；
5. API请求携带正确的 `X-Standard-Token`；
6. 服务端配置对应令牌的SHA-256；
7. 标准目录不存在，禁止原地覆盖。

标准管理和标准正文读取默认拒绝。普通匹配仍可以返回候选、分数和证据；只有请求标准正文时才需要标准访问令牌。

## 4. 标准文档产物

```text
var/standard/
├── page-index.json
└── documents/<standard_id>/
    ├── manifest.json
    ├── document.json
    ├── pages/<page_id>.png
    ├── thumbnails/<page_id>.jpg
    └── features/<page_id>.npz
```

清单绑定：

- 来源SHA-256；
- 标准结构文件SHA-256；
- 语义输出摘要；
- Schema版本；
- 指纹算法版本和流水线摘要；
- 渲染DPI；
- 页面图像像素摘要；
- 缩略图文件摘要；
- 特征文件摘要。

## 5. 安全匹配门禁

系统输出三类决定：

- `safe_standard_reuse`；
- `ambiguous`；
- `no_match`。

安全复用至少要求：

- Top-1达到相应总分阈值；
- Top-1与Top-2达到最小间隔；
- 全页哈希与近全页几何证据成立，或局部内点数、内点比例、查询覆盖和变换合理性成立。

`MatchResult` Schema会反向校验自身决定，不能构造一个低于阈值却声明安全复用的结果。

## 6. 完整性与并发

- 已提交运行读取时重新校验run、document、raw和source摘要；
- 标准结构读取时重新校验文件摘要、身份、来源、Schema和语义摘要；
- 特征文件使用前重新校验摘要；
- 标准索引绑定全部标准清单集合，过期索引拒绝使用；
- 标准索引使用带进程与随机令牌的独占锁重建；
- 运行、标准文档和关键命名空间拒绝符号链接；
- 成功产物通过临时目录原子发布；
- 每次失败保留独立记录，不相互覆盖。

## 7. API边界

新增或完成：

- `GET /v1/standard`：需要 `X-Standard-Token`；
- `POST /v1/standard/register`：需要写开关、令牌和人工批准；
- `POST /v1/match`：普通匹配无需令牌；`include_standard=true`需要令牌。

标准令牌只以SHA-256配置：

```bash
DI_STANDARD_ACCESS_TOKEN_SHA256=<64位小写SHA-256>
```

## 8. Rill

Rill Observe Schema为0.2，记录匹配决定、Top-1分数、候选间隔、候选数量和标准结果复用许可。本阶段固定 `shadow_only=true`，不开放Route Assist或boundedAuto。

## 9. 测试与基准

- 67项测试全部通过；
- 分支覆盖率80.66%；
- 本地确定性静态门禁检查53个Python文件，无违规；
- Phase 1和Phase 2验证脚本通过；
- wheel分发验证通过；
- 合成匹配回归9/9通过；
- 已知页回归召回100%；
- 未知及重复页错误安全复用为0。

详见：

- `docs/phase-2/MATCHING_BENCHMARK.md`；
- `docs/phase-2/verification.json`；
- `docs/phase-2/distribution_verification.json`；
- `docs/phase-2/static_sanity.json`。

## 10. 当前限制

1. 合成回归集不能替代真实生产黄金集；
2. 外部解析器仍默认禁用，未完成真实模型资格测试；
3. 尚未完成大规模索引和并发压力测试；
4. PyMuPDF许可证选择仍阻断不兼容AGPL的闭源生产发行；
5. 当前离线环境未能安装Ruff和Mypy，二者只在CI中配置，不能在本地报告为通过；
6. Rill仍只允许Shadow。

## 11. 阶段结论

Phase 2工程实施和本地回归门禁通过，可以作为Phase 3通用结构恢复的开发基线。生产资格仍为有条件通过，必须完成真实黄金集、外部解析器资格、许可证和正式CI门禁。
