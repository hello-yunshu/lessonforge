# Phase 12 Release Candidate运维规范

## 部署边界

仅支持单节点、自托管、一个活动API进程对应一个本地POSIX工作区。服务应位于可信TLS
反向代理之后，宿主端口只绑定回环或私有网络。多节点、共享工作区和公共SaaS不受支持。

## 生产启动必需项

- `DI_DEPLOYMENT_PROFILE=production`
- 绝对路径 `DI_WORKSPACE`
- `DI_API_TENANT_TOKENS_SHA256_JSON`
- `DI_SINGLE_NODE_MODE=true`
- Reference Rill关闭
- 所有启用写权限域配置对应摘要令牌
- PyMuPDF渲染启用时提供许可证已解决证明

## 容器

Compose要求 `DI_PYTHON_BASE_IMAGE` 为带SHA-256摘要的基础镜像。默认宿主绑定
`127.0.0.1:8080`，容器只读根文件系统、丢弃capabilities、启用no-new-privileges并限制
PID、CPU和内存。未提供digest-pinned基础镜像时构建应失败。

## 备份恢复

```bash
python scripts/workspace_backup.py create /data /backup/workspace.zip
python scripts/workspace_backup.py verify /backup/workspace.zip
python scripts/workspace_backup.py restore /backup/workspace.zip /restore-empty
```

恢复目标必须为空。工具拒绝符号链接、路径穿越、重复成员、异常压缩比、超大成员和摘要
不匹配。备份文件仍可能包含敏感文档，必须由主机或存储层加密并限制访问。

## 发布门禁

```bash
make verify
make report
make package
```

正式CI还必须通过Ruff、Mypy、pip-audit、覆盖率、Phase 1—12、SBOM、密钥扫描和两次
可复现wheel构建。任何门禁失败都不得发布。

## 回滚

发行资产不可覆盖。部署时保持`current`、`staging`和`rollback`目录；新版本必须先在
staging执行冻结验证、readiness、样本文档回放和工作区恢复演练，再原子切换。失败时
恢复旧程序版本；数据格式若已写入新记录，必须依照1.x兼容策略读取，禁止直接删除审计
记录。
