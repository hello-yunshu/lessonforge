# Phase 5 运维说明

## 默认安全状态

```text
DI_RILL_SHADOW_BACKEND=disabled
DI_ENABLE_RILL_SHADOW_WRITES=false
DI_RILL_REFERENCE_BACKEND_ALLOWED=false
```

## 真实Runtime

`DI_RILL_RUNTIME_COMMAND_JSON`必须是JSON参数数组，而不是Shell字符串。正式环境优先使用 `doc-intelligence rill install` 生成的完整 managed bundle；若采用显式 unmanaged command，必须同时提供固定 SHA-256 的 Runtime/model/handler、独立信任密钥，并显式设置 `DI_RILL_ALLOW_UNMANAGED_STABLE_V2=true`。production Stable v2 缺少这些条件时启动直接失败，不会静默降级成“不可用”。

## Reference后端

只用于本地测试：

```text
DI_RILL_SHADOW_BACKEND=reference
DI_RILL_REFERENCE_BACKEND_ALLOWED=true
```

不得用于生产质量声明。

## 状态目录

```text
var/rill-shadow/
├── evaluations/
├── feedback/
├── snapshots/
├── resets/
└── drift/
```

发布包必须排除其中所有运行时文件，仅保留 `.gitkeep`。

## 故障处理

- Runtime超时/退出：关闭进程，防止迟到响应串入下一个请求；主系统继续静态路径。
- feature schema不匹配：拒绝握手。
- generation不匹配：拒绝请求，不提交状态。
- store摘要不匹配：按P0损坏处理，不自动修复。
- 漂移告警：阻断Assist候选，不自动回滚或改路由。
- reset：必须先生成可验证快照。
