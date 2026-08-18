# Phase 2 标准文档匹配基线

> 本报告只验证项目内小型合成回归集，不代表真实行业数据上的最终准确率。

| 用例 | 期望 | 实际 | 正确页 | Top-1 | 间隔 | 耗时(ms) | 通过 |
|---|---|---|---|---:|---:|---:|---|
| full:std_5987170714cb27a1360d14af:0 | safe_standard_reuse | safe_standard_reuse | True | 1.0000 | 0.5184 | 487.871 | 是 |
| crop:std_5987170714cb27a1360d14af:0 | safe_standard_reuse | safe_standard_reuse | True | 0.8623 | 0.3344 | 318.989 | 是 |
| full:std_e7078c7b669687502ac6d08f:0 | safe_standard_reuse | safe_standard_reuse | True | 1.0000 | 0.5765 | 387.891 | 是 |
| crop:std_e7078c7b669687502ac6d08f:0 | safe_standard_reuse | safe_standard_reuse | True | 0.7861 | 0.2187 | 290.866 | 是 |
| full:std_e7078c7b669687502ac6d08f:1 | safe_standard_reuse | safe_standard_reuse | True | 1.0000 | 0.5760 | 406.339 | 是 |
| strong-local-below-configured-threshold | no_match | no_match | True | 0.8623 | 0.3344 | 223.453 | 是 |
| unknown-text | no_match | no_match | True | 0.6268 | 0.4780 | 276.779 | 是 |
| unknown-noise | no_match | no_match | True | 0.6049 | 0.0646 | 157.767 | 是 |
| duplicate-page-ambiguity | ambiguous | ambiguous | True | 1.0000 | 0.0000 | 365.164 | 是 |

## 门禁结果

- 用例总数：9；
- 通过：9；
- 已知页召回：100.00%；
- 未知/歧义页错误安全调用：0；
- 中位匹配耗时：318.989 ms；
- 阶段门禁：通过。

生产冻结前仍需使用真实扫描、拍照、压缩、裁剪、透视和跨版本文档扩大黄金集。
