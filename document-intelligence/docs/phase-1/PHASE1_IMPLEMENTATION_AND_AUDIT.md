---
title: Phase 1 通用解析基线实施与冻结审计
project: document-intelligence
version: 0.1.0
status: engineering-complete-external-qualification-pending
date: 2026-08-02
---

# Phase 1 通用解析基线实施与冻结审计

## 1. 实施结论

本次从仅包含开发文档的空项目开始，已经完成 Phase 1 所需代码，并补齐 Phase 0 的必要前置协议。

**工程实现通过；生产冻结为有条件通过。**

条件只涉及当前离线环境中没有安装 PaddleOCR、OpenDoc 和 MinerU 的固定模型/镜像产物。因此三者已经完成可替换网关、身份校验、版本校验、摘要门禁、统一输出和合约测试，但不能声称已经完成真实准确率横评。真实产物接入后必须运行资格脚本和同一黄金集。

## 2. 已完成内容

### Phase 0 前置

- 严格 Pydantic 核心 Schema；
- 归一化坐标和像素坐标；
- Evidence 强制关联；
- ParseRun、资源消耗、警告和错误结构；
- Parser SDK 和注册表；
- Domain Pack 最小 SDK 与通用示例包；
- P0/P1/P2 错误分级；
- Rill Observe v0.1 草案，强制 `shadow_only=true`；
- JSON Schema 导出；
- 两项 ADR。

### Phase 1

- 文件类型、大小和哈希导入；
- 可运行的 Native PDF 解析器；
- 原生文字、图片、坐标、阅读顺序候选和证据输出；
- 纯扫描 PDF 明确识别为无原生文字层；
- PaddleOCR 3.7.0 网关适配；
- OpenDoc/OpenOCR 0.1.5 网关适配；
- MinerU 3.3 对照网关适配；
- 外部解析器地址、版本和 SHA-256 fail-closed；
- 自动路由：扫描 PDF 可在存在后续 OCR 候选时继续尝试；
- 原始输出留存；
- 成功运行原子提交；
- 失败记录与标准结果目录隔离；
- FastAPI 和 CLI；
- 三类复杂文档夹具；
- 横向报告、依赖摘要、错误库和资格脚本；
- Dockerfile、Compose 和 CI。

## 3. 核心门禁

| 门禁 | 结果 | 证据 |
|---|---|---|
| 同一输入可复现 | 通过 | 五轮回放语义摘要一致 |
| 解析器可替换 | 通过 | Parser Protocol、Registry、统一网关合约 |
| 失败不污染标准结果 | 通过 | 独立失败记录、标准目录快照回归测试 |
| 所有对象可追溯 | 通过 | Element/Relation 必须引用 Evidence |
| 核心不含单一领域术语 | 通过 | 自动静态检查 |
| 外部服务版本不符时阻断 | 通过 | 健康及解析结果双重校验 |
| 外部摘要缺失或不符时阻断 | 通过 | `required_artifact_sha256` 门禁 |
| Rill 不执行生产动作 | 通过 | Observe Schema 固定 Shadow |
| 基础 API 可运行 | 通过 | 真实 Uvicorn + curl 冒烟 |
| 单测和合约测试 | 通过 | 24项测试全部通过 |
| 覆盖率 | 通过 | 约83%，门禁80% |
| Python编译 | 通过 | `compileall` |

## 4. 实测结果

- 原生文本 PDF：1页，7个文字/标题元素；
- 纯扫描 PDF：1个图片元素，返回 `EMPTY_NATIVE_TEXT`；
- 图文混排 PDF：2页，5个文字元素和1个图片元素；
- 重复运行的 run ID 和语义输出摘要稳定；
- CLI 解析成功；
- Uvicorn 的 `/healthz`、`/v1/parsers`、`/v1/parse` 冒烟成功。

详细数据：

- `PARSER_BENCHMARK.md`；
- `benchmark_results.json`；
- `DEPENDENCY_LOCK.md`；
- `verification.json`。

## 5. 当前未冒充完成的事项

### P1：外部模型真实资格测试尚未执行

原因：执行容器无外网，且没有预装固定 PaddleOCR、OpenDoc 和 MinerU 模型产物。

这不影响核心代码和网关协议完成，但会阻止生产冻结。后续必须：

1. 固定容器或模型文件；
2. 写入其 SHA-256；
3. 启用一个外部解析器；
4. 运行 `scripts/qualify_external_parser.py`；
5. 在相同黄金集比较准确率、耗时和资源；
6. 许可证审核通过；
7. 再修改冻结状态。

### P2：本地静态工具未执行

当前内部离线包索引无法获取 Ruff 和 Mypy，故本地仅完成 AST 安全检查、编译和测试。CI 已配置 Ruff、Mypy、测试和覆盖率；在有可用依赖源的标准构建环境中必须执行。

### 环境提示

共享Python环境中的 `moviepy` 与已安装 Pillow 12.2.0 存在既有约束冲突；本项目不依赖 moviepy。正式构建应使用隔离虚拟环境或容器，不能依据共享环境的全局 `pip check` 作为项目自身依赖结论。

## 6. 第一阶段冻结意见

- 可以作为 Phase 2“标准文档匹配”的开发基线；
- Native PDF 路线可以用于开发与内部测试；
- PaddleOCR、OpenDoc、MinerU 默认继续禁用；
- 不得把扫描 PDF 的 Native 结果解释为 OCR 已完成；
- 不得开放外部解析器，除非版本、摘要、资格报告全部满足；
- 不得把任何失败运行写入标准结果库；
- Rill 仍保持 Shadow 事件草案，不进入 Route Assist。
