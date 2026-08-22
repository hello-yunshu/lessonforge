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
- upstream latest Stable：`1.2.0`
- immutable `stable-index.json` SHA-256：`fb876573dab2f563a63ffa02e3b7faf62f7348b166f0cb752f59de6bba937e06`

上游来源：[RillML v1.2.0 release](https://github.com/hello-yunshu/rill-ml/releases/tag/v1.2.0)。

## 实现结果

1. `defaults/rill_adoption.json` 是唯一采用锁，固定 supported/tested、tag、commit、schema、API、protocol、签名信任根和 index digest。
2. `rill/adoption.py` 校验签名 index、HTTPS immutable-tag URL、artifact 身份、版本、平台、libc、大小和 SHA-256；文件校验采用 streaming digest，并拒绝 symlink。
3. `rill/distribution.py` 提供完整 Runtime/model/handler adoption bundle 的下载/验签、临时 staging、Stable v2 handshake/health/invoke qualification、原子激活、previous-good、整包回滚、跨进程锁和 fail-closed 错误码；`--version` 单独成功不能激活 bundle。
4. `rill/stable_protocol.py` 与 `rill/stable_client.py` 实现 Stable IPC v2 的 Handshake、Health、Invoke、requestId、边界大小、超时、broken pipe、stderr、异常响应和 capability 校验。
5. Stable 生产路径不使用现有 Python v3 语义。Stable v2 的 feedback、snapshot、reset 明确标记为 Host-owned；Runtime update capability 默认不声明，Runtime reset 永远为 false。
6. 新增 LessonForge-owned Handler API v1 WASM component 和 bounded model；它们不依赖或编译 `rill-runtime`，由官方 Runtime 1.2.0 加载，根 Actions 对真实 `RillShadowService.evaluate`、Host feedback、snapshot/reset 做业务 E2E。
7. `/healthz`、`/v1/rill/status` 和 Web Status 页显示 latest Stable、supported、tested、完整 bundle qualification、model/handler identity、Stable API/protocol 及 Preview 状态。
8. 根 workflow 已接管 backend quality/tests/security/package/web/distribution/business E2E/negative gates；嵌套旧 workflow 已移除并在 `docs/ci-reference/` 明确标记为 `NOT_EXECUTED_BY_GITHUB_ACTIONS`。

## 本轮验证边界

- 按本轮执行提示词，本地源码阶段不运行 pytest、Ruff、Mypy、构建、wheel smoke 或 real Runtime smoke；这些门禁统一交给根 GitHub Actions。
- 本文件描述的是实现边界，不是 Actions 结果；源码完成后只记录 workflow/run 的真实状态，不把触发或 workflow 文件存在写成 PASS。

## 尚未可称为完整 PASS 的边界

- 官方 Stable v2、LessonForge handler/model、生产启动链、全量 CI 和负向门禁的最终结果均待本轮 push 后的 Actions。

结论：源码目标是让 LessonForge 只声明并实际消费 RillML 1.2.0 Stable v2；远程 Actions 结论仍是独立发布边界。
