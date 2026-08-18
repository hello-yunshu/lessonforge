# Phase 8复审与Phase 9 / 1.0冻结审计

## 审计基线

以 `document-intelligence_phase8_0.8.0.zip` 独立解压内容为唯一输入。基线192项测试通过后才开始修改。

## Phase 8复审结论

Phase 8的多领域隔离、Domain Pack SDK和跨领域基准可以进入1.0冻结，但原代码尚缺少机器可验证的稳定契约清单。另发现Domain Pack注册表在初始化时持久化空状态，以及CLI存在重复位置参数定义。这些问题均在1.0冻结前修复。

## Phase 9推进内容

- 建立10类冻结契约、双层SHA-256及独立代码信任锚；
- 冻结核心Schema、Parser SDK、Domain Pack SDK和Rill事件；
- 冻结权限、发布、回滚、审计和既有REST操作，并以AST从API源码反向发现实际路由；
- 形成1.x版本与迁移政策；
- 新增API、CLI、Schema、基准与发布验证；
- 将项目、Domain Runtime和检测器推进到1.0.0；
- 使六个内置Domain Pack兼容1.x。

## 审计结论

1.0工程冻结可以通过。冻结清单不仅校验内部摘要，还由代码中的独立v1信任锚约束；冻结REST操作同时由API源码AST发现结果验证，不能通过同步修改清单与摘要掩盖删除。不得将该结论描述为生产已就绪。冻结清单明确保留五项生产阻断，且`production_qualified=false`。不存在生产Champion、Assist激活或boundedAuto开启状态。
