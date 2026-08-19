# document-intelligence

通用复杂文档智能解析、标准文档匹配、结构恢复与领域适配平台。当前版本 **1.0.3-rc.1** 已完成：

- Phase 0：核心协议；
- Phase 1：通用解析基线及复审修复；
- Phase 2：标准文档库、全页/局部截图匹配和安全标准结果调用；
- Phase 3：阅读顺序、标题层级、内容分组、图文关联、跨页关系和整文档一致性；
- Phase 4：声明式 Domain Pack Runtime、完整性与兼容性校验、领域结果隔离和审核桥接；
- Phase 5：真实 RillML IPC v3 Shadow适配、静态基线、延迟反馈、离线回放、漂移监视与快照；
- Phase 6：资格门禁、人工激活、Tier 1白名单、第二解析器/高分辨率/专家解析器候选、审核优先级、隔离队列与可逆解析器熔断；
- Phase 7：主动学习、DVC/MLflow血缘、黄金与挑战门禁、Candidate/Shadow/Champion、灰度证明与一键回滚；
- Phase 8：多领域内置包、声明式领域脚手架、建议性文档族识别与跨领域隔离回归；
- Phase 9：核心Schema、Parser SDK、Domain Pack SDK、Rill事件、权限、发布、回滚与审计格式的1.0机器冻结；
- Phase 10：真实数据、固定解析器、规模恢复、供应链、许可证与试运行证据的生产资格门禁；
- Phase 11：生产资格活动编排、租约、检查点、证据链接、哈希链事件和密封恢复包；
- Phase 12：发布候选安全收口、租户认证、访问审计、受限容器、供应链证据与可复现构建；
- `boundedAuto`仍硬关闭，默认配置不激活Assist动作，也不创建生产模型别名。

## 快速开始

```bash
python -m pip install -r requirements/development.txt
python -m pip install --no-deps -e .
python scripts/generate_fixtures.py
doc-intelligence freeze-verify
pytest -q
uvicorn document_intelligence.api.main:app --reload --port 8080
```

解析和恢复通用结构：

```bash
doc-intelligence parse tests/fixtures/native_text.pdf --parser native-pdf
doc-intelligence structure-recover <parse_run_id> --output structure.json
```

列出、安装和启用声明式 Domain Pack：

```bash
export DI_ENABLE_DOMAIN_PACK_WRITES=true
doc-intelligence domain-pack-builtin-list
doc-intelligence domain-pack-install-builtin technical-manual --activate
doc-intelligence domain-pack-list
```

Rill Shadow本地开发（Reference后端仅用于测试）：

```bash
export DI_RILL_SHADOW_BACKEND=reference
export DI_RILL_REFERENCE_BACKEND_ALLOWED=true
export DI_ENABLE_RILL_SHADOW_WRITES=true
doc-intelligence rill-shadow-inspect
```

真实Runtime必须通过 `DI_RILL_RUNTIME_COMMAND_JSON` 提供明确参数向量，并通过IPC v3握手、feature schema hash及capability检查。Reference后端不会冒充真实Runtime。

应用领域包并导出审核任务：

```bash
doc-intelligence domain-apply <structure_id> generic-document --output domain.json
doc-intelligence domain-review-export <domain_result_id> --output review.json
```

Domain Pack 只允许声明式 YAML/JSON 入口，不执行包内 Python、Shell 或动态代码。领域结果与
通用解析、结构结果分开保存；失败默认返回无领域断言的通用回退结果。

MLOps本地治理示例：

```bash
export DI_ENABLE_MLOPS_WRITES=true
doc-intelligence mlops-active-select --max-items 50
doc-intelligence mlops-inspect
```

模型别名切换还必须单独设置`DI_ENABLE_MLOPS_RELEASE=true`。DVC与MLflow作为外部系统接入，核心只接受不可变摘要和运行证明，不执行训练脚本。

生产资格证据治理示例：

```bash
export DI_ENABLE_PRODUCTION_QUALIFICATION_WRITES=true
doc-intelligence production-inspect
doc-intelligence production-dataset-record gold-evidence.json
doc-intelligence production-qualify qualification-request.json
```

资格报告即使为 `qualified=true`，也固定 `automatic_release_authorized=false`；
它不能自动发布模型、打开Rill Assist或改变解析结果。

生产资格活动编排示例：

```bash
export DI_ENABLE_QUALIFICATION_CAMPAIGN_WRITES=true
doc-intelligence campaign-create campaign.json
doc-intelligence campaign-inspect
```

活动编排只组织外部真实验证工作，不执行任意脚本、不生成真实证据，也不会自动发布。
备份恢复同时要求资格活动和生产资格两个写权限域。

## 管理安全

生产档会对所有 `/v1` 接口统一要求 `X-API-Token`、`X-Tenant-ID` 和
`X-Subject-ID`。解析、结构、领域和Rill结果按租户授权；服务端只保存令牌
SHA-256，不保存明文令牌。生产档只支持单节点自托管部署，并应放在可信TLS
反向代理之后。

Domain Pack、标准库、Rill、MLOps及资格治理还保留各自独立的管理令牌和写入开关：

```bash
export DI_ENABLE_DOMAIN_PACK_WRITES=true
export DI_DOMAIN_PACK_ACCESS_TOKEN_SHA256="$(python - <<'PY'
import hashlib
print(hashlib.sha256(b'replace-with-a-long-random-token').hexdigest())
PY
)"
```

生产环境还应启用签名验证并配置历史可验证的 Ed25519 公钥环。

## 文档

- 完整研发规范：`docs/01_复杂文档智能解析平台_完整开发设计与实施规范_v1.0.md`
- 1.0冻结审计：`docs/audits/CODE_AUDIT_AND_PHASE9_FREEZE_2026-08-04.md`
- Phase 9实施与自审：`docs/phase-9/PHASE9_IMPLEMENTATION_AND_AUDIT.md`
- 1.0冻结清单：`docs/phase-9/FROZEN_CONTRACTS_V1.json`
- 1.0冻结基准：`docs/phase-9/ONE_ZERO_FREEZE_BENCHMARK.md`
- 1.0 API：`docs/api/REST_API_1_0.md`
- 1.0运维：`docs/operations/ONE_ZERO_OPERATIONS.md`
- 版本与迁移政策：`docs/compatibility/SEMVER_AND_MIGRATION_POLICY.md`
- Phase 10实施与自审：`docs/phase-10/PHASE10_IMPLEMENTATION_AND_AUDIT.md`
- 生产资格基准：`docs/phase-10/PRODUCTION_QUALIFICATION_BENCHMARK.md`
- Phase 10 API：`docs/api/REST_API_PHASE10.md`
- Phase 10运维：`docs/operations/PHASE10_OPERATIONS.md`
- Phase 11实施与自审：`docs/phase-11/PHASE11_IMPLEMENTATION_AND_AUDIT.md`
- Phase 11编排基准：`docs/phase-11/QUALIFICATION_CAMPAIGN_BENCHMARK.md`
- Phase 11 API：`docs/api/REST_API_PHASE11.md`
- Phase 11运维：`docs/operations/PHASE11_OPERATIONS.md`
- Phase 12实施与自审：`docs/phase-12/PHASE12_IMPLEMENTATION_AND_AUDIT.md`
- Phase 12发布候选基准：`docs/phase-12/RELEASE_CANDIDATE_BENCHMARK.md`
- Phase 12 API：`docs/api/REST_API_PHASE12.md`
- Phase 12运维：`docs/operations/PHASE12_OPERATIONS.md`
- 发布候选推进审计：`docs/audits/CODE_AUDIT_AND_PHASE12_ADVANCEMENT_2026-08-04.md`
- 当前项目状态：`docs/PROJECT_STATUS.md`

## 发布与生产资格边界

`1.0.3-rc.1` 是**受限单节点自托管发布候选版**，不是无条件生产稳定版。核心原生PDF
文本与嵌入图像提取已使用 `pypdf`；PyMuPDF仅作为可选像素渲染器，生产档默认关闭，
必须完成许可证证明后才能显式启用。

当前发行包没有预置真实黄金集、固定外部解析器资格、168小时持续运行、正式试运行或
`qualified=true` 生产报告。Ruff、Mypy、pip-audit与正式SBOM门禁已进入唯一CI流程，
但本地离线环境缺少部分工具，因此相应结果不会被虚报为本地通过。`boundedAuto`继续
硬关闭。
