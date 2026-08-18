# Phase 6 Rill Assist Benchmark

## 结论

Phase 6确定性工程回归共8项，8项通过。该基准用于验证资格、隔离、幂等、可逆和默认关闭，不代表真实文档生产准确率，也不能代替真实专家反馈资格测试。

## 覆盖场景

1. Reference Runtime不能取得生产Assist资格；
2. Runtime、模型包、Handler固定SHA-256缺一不可；
3. 审核任务只增加不可变队列记录，重复执行幂等；
4. 激活级小时限流在阻断时仍留下审计记录；
5. 第二解析器只生成候选运行，不替换来源结果；
6. 异常解析器暂停必须绑定漂移告警，可由操作员恢复；
7. boundedAuto保持硬关闭；
8. 所有Tier 1执行记录均声明`replaced_existing_result=false`。

机器可读结果见`benchmark_results.json`。
