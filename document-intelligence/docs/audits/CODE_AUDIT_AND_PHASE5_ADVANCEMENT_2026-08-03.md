# Phase 4复审与Phase 5推进审计（2026-08-03）

## 输入基线

- 独立解压：`document-intelligence_phase4_0.4.0.zip`
- 输入ZIP SHA-256：`99d75b42c530f78a0a5d60d16d41a788c3be932d2d06f0e20b32c66b970867d7`
- Phase 4基线测试：110项通过

## 审核判断

Phase 4可作为Phase 5基线，但之前只有Observe草案，没有真实Rill Runtime协议、决策账本、延迟反馈、状态恢复材料、漂移状态完整性和离线对照指标。因此本轮严格限定为Shadow控制面，不提前实现Phase 6动作执行。

## Rill源契约核对

核对公开仓库 `hello-yunshu/rill-ml`：Stable 1.1.0，Preview 0.15.0；Runtime IPC v3为opt-in Preview，支持Observe、Decide、Feedback、Inspect、Snapshot、Reset，并具有deadline、feature schema hash及generation字段。项目实现以该契约为准，没有将HTTP模拟接口冒充正式Rill。

## 推进结果

完成版本0.5.0。详细能力、问题与门禁见 `docs/phase-5/PHASE5_IMPLEMENTATION_AND_AUDIT.md`。

## 审计结论

- Phase 5工程完成；
- 所有Rill结果固定Shadow；
- 无生产动作执行器；
- 主解析系统在Rill失败时保持可用；
- 可作为Phase 6候选基线；
- Phase 6不得自动开启，必须先积累真实人工反馈并通过静态基线对照。

## 实施后反向自审补充

冻结前继续从幂等性、真实IPC兼容、存储替换攻击和状态一致性反向审查，确认并修复：

- evaluation幂等键绑定后端与generation，避免旧不可用结果或反馈前决策被永久复用；
- IPC v3 Handler API精确限定为v1，capability列表严格唯一且有界；
- 26项特征顺序及9个动作臂由冻结Schema双向校验；
- 缺失记录与损坏记录语义分离，API缺失查询返回404；
- Rill命名空间每次访问重新校验符号链接；
- snapshot竞争提交后重新验证完整语义；
- 漂移告警身份绑定阈值且可检测篡改；
- Runtime reset失败时恢复宿主漂移状态；
- 第三方许可证清单补充RillML/rill-runtime。

最终本地结果：133项测试通过，分支覆盖率80.23%，Phase 1—5门禁及7/7合成Shadow基准通过。该结果不等同于真实签名Runtime和真实流量资格测试。
