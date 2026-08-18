# Phase 1 架构

```text
Upload / CLI
    ↓
Ingestion Policy
    ↓
ParseRequest + SHA-256
    ↓
Parser Registry / Static Router
    ├── NativePdfParser（本阶段真实运行）
    ├── PaddleParser（统一网关、fail closed）
    ├── OpenDocParser（统一网关、fail closed）
    └── MinerUBenchmarkParser（仅对照、fail closed）
    ↓
ParsedDocument + Evidence + ParseRun
    ↓
Schema / hash / parser identity validation
    ↓
Atomic Artifact Store
    ├── raw/{run}.json
    └── runs/{run}/document.json + run.json + manifest.json
```

## 关键边界

- `standard/` 不在解析提交事务中。
- 外部引擎没有固定摘要时不可用。
- 相同输入、解析器、版本和配置生成相同 run ID 和语义摘要。
- 时间戳与原始输出路径不进入语义摘要。
- 供应商私有格式只存在于网关内部。
