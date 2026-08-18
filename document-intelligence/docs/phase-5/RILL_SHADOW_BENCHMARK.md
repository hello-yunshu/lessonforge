# Phase 5 Rill Shadow Benchmark

机器可读结果见 `benchmark_results.json` 和 `verification.json`。

本基准覆盖：重复评估幂等、无生产动作、延迟反馈、快照完整性、Inspect边界、Runtime缺失隔离以及Reference身份隔离。所有样本均为确定性合成样本，不代表真实文档、真实人工流量或真实 Rill 签名 handler 的线上质量。

Rill 与静态策略的准确率只有在真实审核反馈进入后才有统计意义。Phase 5 不会根据合成结果开启 Assist。


冻结时机器可读基准为7/7通过，生产动作计数为0；完整自动回归为133项通过，分支覆盖率80.23%。这些数字只证明当前实现和确定性夹具的行为，不推断真实Runtime策略质量。
