# Phase 8 跨领域回归基准

## 结论

确定性跨领域回归 **5/5 通过**，文档族候选识别准确率 **100%**。该基准用于验证领域扩展不会污染通用核心，不代表真实生产文档准确率。

| 文档族 | 预期 Domain Pack | 结果 |
|---|---|---|
| 教育内容 | `education-content` | 通过 |
| 试卷 | `examination-paper` | 通过 |
| 学术论文 | `academic-paper` | 通过 |
| 法律合同 | `legal-contract` | 通过 |
| 技术手册 | `technical-manual` | 通过 |

## 强制断言

- `ParsedDocument` 核心 Schema SHA-256 保持为 `9e8be89228dd68a4f65aec8832bc89b75ff29217c9f7a5842d4f93666bacb09a`；
- 每个领域结果只包含其本体声明的对象类型；
- 所有领域对象和关系保留证据引用；
- Domain Pack 执行不会修改通用解析结果；
- 文档族检测只产生候选，不自动激活或执行领域包；
- `boundedAuto=false`。

机器可读结果：`CROSS_DOMAIN_BENCHMARK.json`。
