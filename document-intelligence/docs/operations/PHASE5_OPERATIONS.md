# Phase 5 运维说明

## 默认安全状态

```text
DI_RILL_SHADOW_BACKEND=disabled
DI_ENABLE_RILL_SHADOW_WRITES=false
DI_RILL_REFERENCE_BACKEND_ALLOWED=false
```

## 真实Runtime

`DI_RILL_RUNTIME_COMMAND_JSON`必须是JSON参数数组，而不是Shell字符串。正式环境应指向固定SHA-256的 `rill-runtime`、签名模型包、签名handler和独立信任密钥。Runtime启动失败只会把Rill状态标记为不可用，不会阻止解析API启动。

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
