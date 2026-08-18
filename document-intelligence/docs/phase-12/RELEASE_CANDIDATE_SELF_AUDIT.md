# Phase 12 发布候选独立自审

## 结论

- 受限单节点自托管发布候选：**有条件通过**；
- 公网多租户SaaS：**不通过**；
- 生产稳定版：**不通过**；
- 生产资格：**未取得**；
- `boundedAuto`：**硬关闭**。

## 复检数据

- 241项测试、57个测试文件全部通过；
- 四批实测累计墙钟时间60.24秒；
- 综合覆盖率80.26%，语句覆盖率84.80%，分支覆盖率63.87%；
- Phase 1—12门禁和Phase 12基准通过；
- 本地未安装Ruff、Mypy和pip-audit，未虚报正式工具证据。

## 原发布审计问题闭环

| 编号 | 事项 | 当前状态 |
|---|---|---|
| P0-01 | 核心API统一认证、租户隔离和限流 | closed-for-rc |
| P0-02 | 项目许可证与发行元数据 | closed |
| P0-03 | PyMuPDF发行许可耦合 | closed-for-base-rc |
| P0-04 | 真实多领域生产资格 | open-stable-blocker |
| P0-05 | 可复现依赖、容器与构建 | partially-closed-for-rc |
| P0-06 | 当前CI和发布入口 | partially-closed-for-rc |
| P0-07 | 能力声明与解析器资格收窄 | closed-for-rc |
| P1-01 | 可观测性与就绪探针 | closed-for-rc |
| P1-02 | 数据治理、保留、删除和静态加密 | open-restricted-boundary |
| P1-03 | 单节点存储边界 | closed |
| P1-04 | 关键错误分支覆盖 | open-quality-blocker |
| P1-05 | 测试超时和总时长治理 | closed-for-rc |
| P1-06 | 生产assert | closed |
| P1-07 | 容器硬化 | closed-for-rc |
| P1-08 | 维护与发行治理文件 | closed |
| P1-09 | 正式Ruff/Mypy/SBOM/漏洞扫描证据 | partially-closed-for-rc |
| P2-01 | 历史脚本和唯一默认入口 | closed-for-default-path |

## 仍然阻断生产稳定版的事项

1. 真实多领域黄金集、挑战集、固定外部解析器和独立专家证据；
2. 168小时持续运行、规模、重启恢复和真实试运行；
3. 托管CI中的Ruff、Mypy、pip-audit与容器扫描原始结果；
4. 发行资产签名和可验证provenance；
5. 分支覆盖率从63.87%提升到发布审计目标；
6. 敏感数据生命周期、删除、静态加密/KMS的完整产品能力；
7. 启用可选PyMuPDF渲染器时的独立许可证明。

## 发布边界

本包只能标记为 `1.0.3-rc.1`，适用于受限单节点、自托管、可信TLS反向代理后的工程评估。不得描述为生产稳定版，不得默认处理高敏感材料，不得开启自动发布或`boundedAuto`。
