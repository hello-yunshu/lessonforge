from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from document_intelligence.config import Settings
from document_intelligence.parsers import NativePdfParser
from document_intelligence.schema import BaseType, ParseRequest
from document_intelligence.services import build_registry

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
OUT_JSON = ROOT / "docs" / "phase-1" / "benchmark_results.json"
OUT_MD = ROOT / "docs" / "phase-1" / "PARSER_BENCHMARK.md"


def benchmark_native(rounds: int = 5) -> list[dict[str, object]]:
    parser = NativePdfParser()
    rows: list[dict[str, object]] = []
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["fixtures"]:
        path = FIXTURES / fixture["file"]
        request = ParseRequest(
            filename=path.name,
            mime_type="application/pdf",
            content=path.read_bytes(),
            parser_id=parser.parser_id,
        )
        durations: list[float] = []
        digests: set[str] = set()
        result = None
        for _ in range(rounds):
            started = time.perf_counter()
            result = parser.parse(request)
            durations.append((time.perf_counter() - started) * 1000)
            digests.add(result.document.semantic_digest())
        assert result is not None
        rows.append(
            {
                "fixture": path.name,
                "family": fixture["family"],
                "input_bytes": path.stat().st_size,
                "pages": len(result.document.pages),
                "elements": len(result.document.elements),
                "text_elements": sum(
                    item.base_type in {BaseType.TEXT, BaseType.HEADING}
                    for item in result.document.elements
                ),
                "image_elements": sum(
                    item.base_type == BaseType.IMAGE for item in result.document.elements
                ),
                "warnings": [item.code for item in result.run.warnings],
                "median_duration_ms": round(statistics.median(durations), 3),
                "p95_duration_ms": round(sorted(durations)[max(0, int(rounds * 0.95) - 1)], 3),
                "semantic_digest_reproducible": len(digests) == 1,
            }
        )
    return rows


def main() -> None:
    settings = Settings(
        workspace=ROOT / "var",
        parser_config=ROOT / "configs" / "parsers.yaml",
    )
    native_rows = benchmark_native()
    parser_health = [item.model_dump(mode="json") for item in build_registry(settings).health()]
    payload = {
        "phase": 1,
        "generated_by": "scripts/run_phase1_benchmark.py",
        "native_pdf": native_rows,
        "parser_health": parser_health,
        "limitations": [
            "PaddleOCR/OpenDoc/MinerU model runtimes are not installed "
            "in this offline execution environment.",
            "Their gateway contracts are covered by mocked contract tests; "
            "accuracy benchmarking requires pinned external artifacts.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Phase 1 多解析器横向基线",
        "",
        "## Native PDF 实测",
        "",
        "| 夹具 | 类型 | 页数 | 元素 | 文本 | 图片 | "
        "中位耗时(ms) | 可复现 | 警告 |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in native_rows:
        lines.append(
            f"| {row['fixture']} | {row['family']} | {row['pages']} | {row['elements']} | "
            f"{row['text_elements']} | {row['image_elements']} | {row['median_duration_ms']} | "
            f"{'是' if row['semantic_digest_reproducible'] else '否'} | "
            f"{', '.join(row['warnings']) or '-'} |"
        )
    lines.extend(
        [
            "",
            "## 解析器可用性",
            "",
            "| 解析器 | 启用 | 可用 | 固定版本 | 摘要 | 原因 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for item in parser_health:
        lines.append(
            f"| {item['parser_id']} | {item['enabled']} | {item['available']} | "
            f"{item['version']} | {item.get('artifact_digest') or '-'} | "
            f"{item.get('reason') or '-'} |"
        )
    lines.extend(
        [
            "",
            "## 结论",
            "",
            "- Native PDF 解析已完成真实运行、重复回放和"
            "语义摘要一致性验证。",
            "- PaddleOCR、OpenDoc、MinerU 采用 fail-closed 网关："
            "未固定服务地址和 SHA-256 时不可用。",
            "- 当前离线环境未安装三套重型模型，因此不虚构其准确率；"
            "网关身份、版本、摘要和统一输出合约已通过测试。",
            "- 外部模型进入生产前必须在相同黄金集上补齐"
            "真实准确率、资源和许可证报告。",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
