# Phase 2 运维说明

## 1. 安全默认值

```bash
DI_DEFAULT_PARSER=auto
DI_ENABLE_STANDARD_WRITES=false
DI_STANDARD_ACCESS_TOKEN_SHA256=
DI_MATCH_HIGH_THRESHOLD=0.86
DI_MATCH_LOCAL_THRESHOLD=0.78
DI_MATCH_MIN_MARGIN=0.08
DI_MATCH_MIN_LOCAL_INLIERS=10
```

未配置标准访问令牌时，标准列表、注册和标准正文返回全部拒绝。普通匹配不受影响。

生成令牌摘要示例：

```bash
python - <<'PY'
import hashlib
print(hashlib.sha256(b'replace-with-a-long-random-token').hexdigest())
PY
```

原始令牌只能保存在密钥管理系统中，不能写入代码仓库、日志或配置清单。

## 2. 工作目录

```text
var/
├── runs/
├── raw/
├── sources/
├── assets/
└── standard/
```

部署时工作目录必须使用持久卷。容器根文件系统保持只读，只有工作目录具有写权限。禁止其他进程在这些目录中创建符号链接。

## 3. 标准文档入库

1. 使用固定解析器版本产生成功运行；
2. 人工核验原文件、结构、证据和页面渲染；
3. 在单独审核环境设置写开关与访问令牌摘要；
4. 使用请求头提供原始访问令牌；
5. 提供审核人、审核说明和 `approved=true`；
6. 注册完成后立即恢复写开关为关闭；
7. 备份标准库并记录标准清单、索引和源码摘要。

禁止用线上用户反馈、Rill建议或单一模型高置信度直接写标准库。

## 4. 匹配决定

- `safe_standard_reuse`：总分、候选间隔和几何证据均通过；
- `ambiguous`：候选相近或证据不足，禁止复用；
- `no_match`：按未知文档进入通用解析。

当前阈值只经过小型合成回归验证。真实生产上线前必须使用真实黄金集重新校准，并将未知文档误接受率设为P0门禁。

## 5. 外部解析器

PaddleOCR、OpenDoc和MinerU默认关闭。启用条件：

- 服务版本固定；
- 容器镜像和模型文件SHA-256固定；
- 健康端点满足统一协议；
- 响应体字节上限生效；
- 真实黄金集资格测试通过；
- 许可证审查完成。

## 6. Rill

Rill继续固定 `shadow_only=true`。不得修改阈值、写标准库、切换生产解析器、发布模型或执行boundedAuto。

## 7. 许可证门禁

Native PDF解析与标准页面渲染当前依赖PyMuPDF。完成兼容AGPL的发行选择、商业许可或替换实现前，不宣称具备不受限制的闭源商业生产发行资格。

## 8. 发布门禁

```bash
python scripts/generate_fixtures.py
PYTHONPATH=src python scripts/run_phase1_benchmark.py
PYTHONPATH=src python scripts/run_phase2_benchmark.py
PYTHONPATH=src python scripts/generate_dependency_report.py
PYTHONPATH=src python scripts/export_schemas.py
PYTHONPATH=src python scripts/verify_phase1.py
PYTHONPATH=src python scripts/verify_phase2.py
python scripts/verify_distribution.py
python scripts/static_sanity.py
pytest --cov=document_intelligence --cov-report=term-missing -q
bash scripts/package_phase2_release.sh
```

Ruff和Mypy由CI执行；离线环境无法安装时不得把它们记录为本地通过。
