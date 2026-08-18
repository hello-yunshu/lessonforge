# Phase 8 运维规范

## 默认关闭

文档族检测写入默认关闭，并使用独立访问令牌。Domain Pack安装仍受原有写入开关、访问令牌和签名策略控制。读取健康状态不会启用任何领域动作。

## 推荐流程

1. 使用`domain-pack-builtin-list`或API查看内置包；
2. 在受控环境安装并人工启用需要的包；
3. 先运行文档族候选检测；
4. 对`ambiguous`和`no_match`送人工审核；
5. 即使结果为`candidate`，仍由上层明确决定是否调用领域执行；
6. 保留检测记录和对应包版本，以维持历史血缘；
7. 新领域发布前必须加入跨领域回归集。

## 安全边界

- 不手工编辑`var/family-detections`；
- 不能卸载被历史检测或领域结果引用的包；
- 不允许Family Profile声明Python、Shell或网络入口；
- 不将用户反馈直接写成Family Profile或黄金真值；
- 不允许领域包修改核心Schema；
- Rill Assist和MLOps发布开关与Family Detection完全独立。

## 监控

关注`candidate/ambiguous/no_match`比例、候选间隔、包版本分布、文档族误判、人工改判率、领域执行失败回退和跨领域回归变化。真实上线前必须建立每个领域独立黄金集。
