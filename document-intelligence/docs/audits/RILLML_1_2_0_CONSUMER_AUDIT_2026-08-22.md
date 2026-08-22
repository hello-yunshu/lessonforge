# LessonForge RillML 1.2.0 consumer复检

日期：2026-08-22
范围：`lessonforge` 对 `hello-yunshu/rill-ml` Stable v1.2.0 的消费、分发、IPC、Host 状态边界、UI 与 CI。

## 已锁定的上游身份

- 仓库：`hello-yunshu/rill-ml`
- tag：`v1.2.0`
- peeled commit：`dc96fdb3bf55eacdd1c093f1be08d1c9daed4400`
- channel：`stable`
- release-index schema：`3`
- stable Runtime API：`2`
- 生产协议：`stable-v2`
- upstream latest：`1.3.0`，仅作 informational，不参与生产选择
- immutable `stable-index.json` SHA-256：`fb876573dab2f563a63ffa02e3b7faf62f7348b166f0cb752f59de6bba937e06`

上游来源：[RillML v1.2.0 release](https://github.com/hello-yunshu/rill-ml/releases/tag/v1.2.0)。

## 实现结果

1. `defaults/rill_adoption.json` 是唯一采用锁，固定 supported/tested、tag、commit、schema、API、protocol、签名信任根和 index digest。
2. `rill/adoption.py` 校验签名 index、HTTPS immutable-tag URL、artifact 身份、版本、平台、libc、大小和 SHA-256；文件校验采用 streaming digest，并拒绝 symlink。
3. `rill/distribution.py` 提供下载、临时 staging、探测、原子激活、previous-good、回滚、进程锁和 fail-closed 错误码。
4. `rill/stable_protocol.py` 与 `rill/stable_client.py` 实现 Stable IPC v2 的 Handshake、Health、Invoke、requestId、边界大小、超时、broken pipe、stderr、异常响应和 capability 校验。
5. Stable 生产路径不使用现有 Python v3 语义。v3 `observe/decide/feedback/inspect/snapshot/reset` 保留为显式 Preview 兼容路径；生产 Stable 的状态、回放、审计、策略和动作执行边界仍由 LessonForge Host 管理。
   上游示例 `echo-handler` 只用于业务中立的官方 Runtime smoke；若启用默认的 `org.lessonforge.shadow.*` capability，仍必须提供并验签匹配的 LessonForge handler，否则 fail closed。
6. `/healthz`、`/v1/rill/status` 和 Web Status 页显示 latest、supported、tested、installed、Stable API/protocol 及 Preview 状态。
7. 新增根目录活动 workflow：后端、Web、分发验签和 Linux 官方二进制 Stable v2 smoke；原有嵌套 workflow 未删除。

## 本地证据

- Stable/Rill 测试：`11 passed`
- 后端全量 pytest：`252 passed, 5 warnings`
- 新 Rill 文件 Ruff format/check：通过
- Web `npm run lint`：0 errors，2 个既有 hook warnings
- Web `npm run check`：通过
- Web `npm run build`：通过；仅有 chunk size warning
- wheel/sdist：构建通过
- clean wheel install：通过，并确认打包包含 adoption lock
- SPDX SBOM：`docs/phase-12/release_sbom.spdx.json` 已重新生成，包含 14 个 Python 包
- 官方 stable index 签名、身份和 immutable digest：通过
- 官方 Linux runtime/model/handler 本地 streaming SHA-256：通过

## 尚未可称为完整 PASS 的边界

- 本机是 macOS，官方 Linux ELF 不能在本机执行，因此官方 Stable v2 真实二进制 smoke：`NOT_RUN`；已放入 Ubuntu CI workflow。
- 远程 GitHub Actions 尚未触发或读取结论：`NOT_RUN`。不能把 workflow 文件存在等同于 CI 绿色。
- 项目既有全量 coverage gate 当前为 `73.04%`，阈值为 `80%`，因此 coverage：`NOT_PASS`。没有为“变绿”而降低阈值。
- 全仓 Ruff：`NOT_PASS`，现有 scripts/业务代码有大量基线诊断；本次新增 Rill 文件的 targeted Ruff 通过。
- 全仓 Mypy：`NOT_PASS`，当前报告 192 个错误/34 个文件；当前新增 adoption/distribution/Stable v2 文件未出现在全量错误行中。
- `pip-audit --strict`：`NOT_PASS`，锁定 requirements 命中 8 个包、68 条漏洞；主要包括 Pillow 12.2.0、cryptography 46.0.4、Starlette 0.50.0、pytest 9.0.2、lxml 5.4.0 和 python-multipart 0.0.29。未自动升级依赖。
- npm 安装阶段已报告 6 个 high，未运行 `npm audit fix`，避免无审查地改变锁定依赖。

结论：RillML 1.2.0 Stable v2 消费链路、锁定和本地验证已完成；跨平台真实运行、远程 CI、全量覆盖率和依赖安全审计仍是发布前边界。
