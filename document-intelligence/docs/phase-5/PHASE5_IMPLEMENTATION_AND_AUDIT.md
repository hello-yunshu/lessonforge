# Phase 5 实施、冻结与自审报告

## 1. 阶段结论

Phase 5 已实现 **Rill Shadow**，项目版本升级为 `0.5.0`。

本阶段只建立观察、建议、延迟反馈、离线回放、漂移告警、快照和重置能力。任何 Rill 输出均以不可执行的建议对象保存，固定字段为：

```text
shadow_only = true
no_action_executed = true
```

解析器选择、标准结果复用、结构恢复、Domain Pack、审核结果、模型、规则和发布状态均不受 Rill 输出影响。Phase 6 Assist 尚未开放。

## 2. 与真实 Rill 的对接

本阶段没有自造一套与 Rill 无关的接口。宿主适配器依据 `hello-yunshu/rill-ml` 当前公开契约实现：

- Stable workspace：`1.1.0`；
- Preview Runtime 组：`0.15.0`；
- IPC：Preview v3；
- 传输：stdin/stdout 逐行 JSON；
- 最大消息：1 MiB；
- 方法：`handshake`、`health`、`observe`、`decide`、`feedback`、`inspect`、`snapshot`、`reset`；
- 状态保护：feature schema hash、model generation、state generation、deadline；
- Runtime、模型包和 handler 均由 Rill 自身的签名及沙箱边界负责；
- 宿主当前只接受与公开 IPC v3 契约一致的 Handler API v1，不以“任意大于等于1”冒充兼容。

`SubprocessRillClient` 以 `shell=False` 启动显式参数向量。握手必须同时验证 Runtime 身份、feature schema hash 和六项 Shadow capability，任何字段、消息长度、请求 ID、generation、错误 retryability 或输出动作不符合契约都 fail-closed。

项目同时提供 `ReferenceRillShadowClient`，但它仅用于确定性测试和开发回放：

- 必须显式设置 `DI_RILL_REFERENCE_BACKEND_ALLOWED=true`；
- 身份明确包含 `reference`，不能冒充 `rill-runtime`；
- 不执行文档处理动作；
- 不作为真实 Rill 性能或正确率证明。

## 3. 主要交付能力

### 3.1 Observe

从不可变的解析、匹配、结构和领域结果中构造通用特征。输入血缘必须相互一致，领域结果必须绑定同一结构和解析运行。

特征顺序单独冻结在：

```text
configs/rill_feature_schema.json
```

Feature schema 包含固定的 26 个浮点特征、缺失值策略、变换方法和 9 个动作臂。Runtime handshake 使用其规范化 SHA-256，而不是模糊的展示型 JSON Schema。

### 3.2 Decide

固定动作臂：

1. `ACCEPT`
2. `RETRY`
3. `REPROCESS_HIGH_RES`
4. `USE_SECONDARY_PARSER`
5. `USE_SPECIALIST_PARSER`
6. `USE_DOMAIN_ADAPTER`
7. `VLM_REVIEW`
8. `HUMAN_REVIEW`
9. `QUARANTINE`

Runtime 只能从宿主 allowlist 中返回动作，动作与 arm index 必须双向一致。Shadow 决策只写入隔离命名空间，不存在动作执行器。

### 3.3 静态基线

`StaticShadowPolicy` 作为可比较基线，处理：

- P0 警告；
- Domain Pack 回退或错误；
- 结构错误及低一致性；
- 标准匹配歧义；
- 空原生文本；
- 低解析置信度；
- 接近匹配但未达到安全复用门禁。

离线回放同时计算静态基线和 Rill 建议相对人工最终动作的准确率，不能只报告 Rill 自身指标。

### 3.4 Feedback

人工结果通过不可变反馈记录进入 Shadow：

- 一次 evaluation 只允许一个最终反馈；
- 不同反馈尝试会被拒绝；
- P0/P1 错误和错误 `ACCEPT` 受到高额惩罚；
- feedback 采用 Runtime v3 decision ledger 字段；
- Runtime 已接受而本地落盘失败时，重试产生的 `duplicateFeedback` 被视为幂等成功，不会重复学习。

### 3.5 Replay 和 Assist 门禁

回放指标包括：

- Rill 与静态策略准确率；
- 建议分歧数；
- P0/P1 上错误 `ACCEPT` 数；
- 平均奖励；
- 平均人工修改时长；
- 漂移告警；
- Assist 候选阻断原因。

Phase 5 固定要求至少 30 条反馈，且不得出现严重错误接受、缺失 Rill 建议、低于静态基线或漂移告警，才会把 `safe_for_assist_consideration` 设为 true。该字段只是后续评审输入，不会自动开启 Assist。

### 3.6 漂移

宿主侧保留一个小型、可审计的安全监视器，确保 Rill Runtime 缺失时仍能发现人工错误率异常。它不是 RillML Page-Hinkley、ADWIN 或 KSWIN 的替代品。

状态采用带 SHA-256 的原子信封保存；告警不可变；更新使用文件锁；进程失败后可根据不可变反馈以及最近一次 reset 重新构建，避免重复反馈或并发更新造成计数漂移。

### 3.7 Snapshot / Reset

- Runtime state 和宿主漂移状态分别校验摘要；
- snapshot ID 由两类状态摘要和 generation 生成；
- 重复快照幂等；
- reset 前强制快照；
- reset 使用 expected state generation；
- reset 记录不可变；
- 当前正式 Runtime v3 没有宿主通用 restore 请求，因此本项目只保存并验证状态，真实恢复仍需由后续签名 handler / Runtime 部署契约提供。Reference Runtime 支持测试恢复，但不冒充生产能力。

## 4. 安全边界

- 默认 `DI_RILL_SHADOW_BACKEND=disabled`；
- 默认 `DI_ENABLE_RILL_SHADOW_WRITES=false`；
- API 默认没有令牌即拒绝；
- Runtime 命令只能是 JSON argv，禁止 shell 字符串；
- Runtime 失败、超时、崩溃、错误输出和协议不兼容均不影响主解析结果；
- Rill 命名空间与 runs、standard、structures、domain-results 分离；
- Runtime 错误经稳定错误码脱敏，不向 API 暴露 stderr 或内部路径；
- evaluation、feedback、snapshot、reset、drift 均进行路径、文件和语义完整性校验；
- 重复 Observe/Decide 仅在“输入事件＋后端身份＋model/state generation”完全一致时返回已验证结果，防止重复学习，同时避免把旧的 Runtime 不可用结论永久冻结；
- 特征顺序、缺失值策略和动作臂由冻结 feature schema 反向校验，代码与配置任一侧漂移都会拒绝启动；
- Runtime 能力必须非空、唯一且有界，Handler API 版本必须精确兼容。

## 5. 自审发现与修复

本阶段自审额外发现并修复：

1. **重复评估会重复 Observe/Decide**：幂等上下文现在绑定输入事件、后端身份以及输入 model/state generation。
2. **旧的 Runtime 不可用结果可能永久冻结同一输入**：后端或 generation 改变后允许重新评估。
3. **反馈改变在线状态后仍返回旧决策**：反馈推进 state generation 后，同一输入可产生新的 Shadow evaluation。
4. **同 ID 并发提交可能静默接受不同内容**：提交前后均比较语义摘要。
5. **snapshot 的时间戳破坏幂等性**：比较时排除非语义时间字段，并在竞争提交后再次比较状态和漂移内容。
6. **Runtime 已学习但本地写入失败时不可安全重试**：IPC v3 `duplicateFeedback` 仅作为同 decision ledger 的幂等确认。
7. **记录不存在被误报为存储损坏**：缺失记录现在保留 `FileNotFoundError`，API稳定返回404；摘要或Schema失败才报告损坏。
8. **命名空间可在服务启动后被符号链接替换**：每次读写和枚举均重新校验根目录及命名空间。
9. **漂移状态裸 JSON 可被篡改**：改为摘要信封和读取校验。
10. **漂移告警ID没有绑定阈值**：告警身份现包含阈值，已存在同ID内容不一致时拒绝接受。
11. **漂移更新可能并发丢失**：增加受限文件锁和基于不可变反馈的重建。
12. **展示型 Observe Schema 被错误当成 feature schema**：拆分严格 Observe JSON Schema 与固定特征顺序 Schema。
13. **代码特征顺序可能与冻结Schema悄然分叉**：启动时校验26项顺序、动作臂、类型和Shadow标记；提取时再次断言顺序。
14. **Runtime capability列表可能重复或越界**：协议层和宿主身份层均要求非空、唯一、长度有界。
15. **Handler API只校验大于等于1过于宽松**：当前宿主精确限定为公开契约支持的API v1。
16. **Runtime reset失败后宿主漂移状态可能已清空**：改为先保存状态，Runtime拒绝时恢复宿主漂移状态；reset前快照仍不可变保留。
17. **旧 Phase 3/4 门禁绑定扁平 Rill 字段**：升级为兼容嵌套结构的门禁，Phase 1—4仍可重放。
18. **Reference Runtime 可能被误解为正式 Rill**：配置、身份、文档和验证均显式区分。
19. **Docker Compose 初次追加环境变量位置错误**：自审中发现并修复，重新进行 YAML 验证。
20. **依赖清单缺少可选Rill运行时**：许可证清单已登记RillML/rill-runtime MIT许可、Preview边界和签名摘要要求。

## 6. 验证结论

阶段合成基准验证的是确定性生命周期和安全隔离，不是生产路由准确率。真实 Rill Runtime 仍需签名 `.rillpack`、`.rillhandler`、信任密钥和固定二进制摘要后进行资格测试。

冻结结论：

| 范围 | 结论 |
|---|---|
| Phase 1—4兼容性 | 通过 |
| Rill IPC v3宿主适配 | 通过 |
| Shadow不执行生产动作 | 通过 |
| 延迟反馈与离线回放 | 通过 |
| 状态完整性与故障隔离 | 通过 |
| 作为Phase 6开发基线 | 通过 |
| Route Assist | 未开放 |
| boundedAuto | 未开放 |
| 无条件生产发布 | 不通过 |

本轮最终验证为133项测试全部通过，分支覆盖率80.23%；Phase 1—5门禁、7/7 Shadow合成基准、静态安全门禁、wheel任意目录导入与安装后CLI均通过。Ruff和Mypy已固定在CI，但当前离线环境未安装，未虚报本地通过。

生产阻断项仍包括真实复杂文档黄金集、真实签名 Rill Runtime/handler 资格测试、外部解析器固定模型测试、大规模并发和故障注入、正式 CI Ruff/Mypy、PyMuPDF发行许可选择。
