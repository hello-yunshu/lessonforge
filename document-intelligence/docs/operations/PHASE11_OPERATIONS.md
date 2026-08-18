# Phase 11 运维规范

## 1. 默认配置

```bash
DI_ENABLE_QUALIFICATION_CAMPAIGN_WRITES=false
DI_QUALIFICATION_CAMPAIGN_ACCESS_TOKEN_SHA256=
DI_QUALIFICATION_CAMPAIGN_MAXIMUM_LEASE_SECONDS=86400
DI_QUALIFICATION_CAMPAIGN_MAX_BUNDLE_BYTES=33554432
```

生产资格写入仍由独立配置控制。不要为方便恢复而让两个权限域共用同一令牌。

## 2. 活动生命周期

```text
planned → running ↔ paused → completed
                    └──────→ cancelled
```

步骤生命周期：

```text
pending → leased → completed
             └──→ failed → pending
```

租约到期后步骤可由其他Worker重新领取。Worker必须以哈希身份提交心跳、检查点、证据和
完成事件。不要把姓名、邮箱或外部系统凭据直接写入事件日志。

## 3. 长期任务

168小时持续运行等任务应：

1. 领取步骤；
2. 周期性心跳；
3. 写入已完成单位、总单位、游标摘要和有限指标；
4. 将外部原始日志保存在受控系统；
5. 只把通过Phase 10登记的不可变证据ID链接到活动；
6. 完成后释放步骤。

活动检查点不是原始日志仓库，也不能替代DVC、MLflow、CI或监控系统。

## 4. 备份与恢复

```bash
doc-intelligence campaign-bundle-export <campaign_id> campaign.zip
doc-intelligence campaign-bundle-verify campaign.zip
doc-intelligence campaign-bundle-import campaign.zip
```

恢复前必须：

- 在隔离环境验证Bundle；
- 确认来源、摘要和密钥管理流程；
- 同时开启活动写入和生产资格写入；
- 备份目标命名空间；
- 恢复后重放活动并重新按当前策略生成资格结论。

历史报告可用于审计，但只有策略摘要与当前策略一致时才能显示为当前资格。

## 5. 事件链与损坏处理

不得手工编辑`var/qualification-campaigns`。发现摘要错误、序号跳跃、前序摘要不一致或
符号链接替换时：

1. 停止写入；
2. 保存只读副本；
3. 从已验证Bundle恢复到新工作区；
4. 比较最后可信事件；
5. 不在损坏目录上继续追加。

## 6. 发布边界

Phase 11只支持资格执行编排。以下行为仍禁止：

- 根据活动完成自动发布；
- 将测试夹具写成现实证据；
- 在步骤中执行Shell；
- 自动缩短资格策略；
- 自动打开Rill Assist或`boundedAuto`。

## 7. 监控建议

至少监控：

- 活动和步骤状态分布；
- 过期租约数量；
- 失败和重试次数；
- 最后事件时间；
- 事件链验证状态；
- Bundle大小和验证失败；
- 当前策略与活动Manifest策略摘要差异。
