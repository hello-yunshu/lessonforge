# Phase 8 实施、冻结与自审报告

## 1. 阶段范围

依据总体规范，Phase 8 只完成：新 Domain Pack 模板、新文档族适配、跨领域通用回归和领域隔离。核心 Schema、Rill协议、MLOps发布门禁与既有证据规则不允许为任何单一领域降低。

## 2. 已实现

### 2.1 Domain Pack SDK

- 新增声明式 `family.yaml`；
- 新增 `family-detection-metadata` 权限和 `family` 入口；
- 新增 basic、classification、relation-heavy 三类脚手架；
- 脚手架只生成 YAML，不生成或执行 Python/Shell；
- 文件清单和 SHA-256 自动进入 manifest。

### 2.2 内置领域包

发行包提供六个可枚举、可按写入门禁安装的内置包：

- `generic-document`；
- `education-content`；
- `examination-paper`；
- `academic-paper`；
- `legal-contract`；
- `technical-manual`。

除通用包外，五个领域包均包含独立文档族特征。它们共享通用 Schema，但本体、规则、验证器、审核标签和结果命名空间互相隔离。

### 2.3 文档族候选检测

- 只读取已启用 Domain Pack 的声明式 Family Profile；
- 综合 MIME、基础对象数量、正向/负向线索、必需线索和候选间隔；
- 输出 `candidate`、`ambiguous` 或 `no_match`；
- 结果绑定文档、结构、检测器、包和Family Profile摘要；
- `no_domain_action_executed=true`为硬约束；
- 不自动安装、启用、执行或发布任何领域包。

### 2.4 不可变存储与历史验证

检测记录原子提交，读取时复核文件摘要、语义摘要、来源解析、结构结果、Domain Pack摘要和Family Profile摘要。参与历史检测的包版本在记录存在时禁止卸载，防止血缘失效。

### 2.5 跨领域回归

固定五类合成文档，验证文档族候选、领域对象、禁用对象、证据完整性、结果隔离和核心Schema摘要。跨领域结果见 `CROSS_DOMAIN_BENCHMARK.md`。

## 3. 自审发现与修复

1. 新版 `education-content` 初始兼容范围错误地排除了旧 Domain Runtime，导致历史Phase 4测试失败；已恢复为 `>=0.4,<1.0`。
2. Family Profile摘要最初依赖模型字段输出顺序；已改为规范化排序JSON摘要。
3. 历史检测只复核包级摘要，没有独立复核Family Profile摘要；已补齐。
4. Domain Pack卸载只检查领域结果引用，未检查文档族检测引用；已增加引用保护。
5. Family Detection Store初始化后若命名空间被替换为符号链接，列表操作可能未重新检查；已在每次路径访问前验证。
6. 旧API测试将Domain Runtime版本写死为0.4.0；已更新为当前0.8.0，同时保持旧包兼容测试。
7. 跨领域YAML中含冒号的未引用文本导致独立脚本解析失败；已修复并加入直接脚本回归。
8. 新代码曾存在超过100字符行；静态安全门禁已恢复为零违规。

## 4. 验证摘要

- 全量自动测试：192项通过；
- 精确分支覆盖率：不低于80%；
- 跨领域基准：5/5通过；
- 核心Schema摘要未变化；
- Phase 1—8兼容门禁通过；
- wheel和完整ZIP独立安装、解压和复验通过；
- `boundedAuto`保持硬关闭。

最终数字以发行时生成的测试、`verification.json`和SHA清单为准。

## 5. 冻结结论

0.8.0满足Phase 8工程冻结要求，可作为Phase 9“1.0冻结”的开发基线。真实生产资格仍依赖真实多领域黄金集、外部解析器资格、规模和并发测试、许可证处理及正式CI的Ruff/Mypy结果。
