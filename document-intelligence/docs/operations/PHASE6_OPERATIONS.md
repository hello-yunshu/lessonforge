# Phase 6 运维规范

## 默认状态

Assist写入和执行均默认关闭，boundedAuto不可配置为true。仅配置访问令牌并不会开启动作。

## 启用前置

1. 使用真实、签名且SHA-256固定的Rill Runtime、模型包和Handler，并确认Runtime `inspect`返回的`artifactDigests`与宿主配置完全一致；
2. 使用真实专家审核结果生成证明；
3. 资格报告无阻断项；
4. 人工创建短期限、低限流、最小动作集合的激活；
5. 配置独立Assist访问令牌；
6. 先开启写入治理，再单独开启执行。

## 紧急回退

- 立即设置`DI_ENABLE_RILL_ASSIST_EXECUTION=false`；
- 调用激活撤销端点；
- 恢复被暂停解析器；
- 保留`var/rill-assist`以供审计，不手工修改记录；
- 基础解析在Assist关闭后继续使用确定性静态路由。

## 监控

重点观察P0/P1错误接受、Rill与静态准确率差、动作分布、每小时执行数、候选运行失败率、隔离队列长度、活跃熔断、Runtime generation、宿主固定摘要以及Runtime `inspect`回报的三类实际加载摘要。
