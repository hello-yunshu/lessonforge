from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

from document_intelligence.matching import MatchDecision, StandardLibrary, StandardMatcher
from document_intelligence.parser_sdk import ParserRegistry
from document_intelligence.parsers import NativePdfParser
from document_intelligence.schema import ParseRequest
from document_intelligence.services import ArtifactStore, ParseOrchestrator

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
OUT_JSON = ROOT / "docs" / "phase-2" / "benchmark_results.json"
OUT_MD = ROOT / "docs" / "phase-2" / "MATCHING_BENCHMARK.md"


def encode_png(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("unable to encode benchmark image")
    return encoded.tobytes()


def register(
    path: Path,
    orchestrator: ParseOrchestrator,
    library: StandardLibrary,
    filename: str | None = None,
):
    request = ParseRequest(
        filename=filename or path.name,
        mime_type="application/pdf",
        content=path.read_bytes(),
        parser_id="native-pdf",
    )
    result = orchestrator.parse(request)
    return library.register_run(
        result.run.parse_run_id,
        reviewer="benchmark-fixture-reviewer",
        approval_note="synthetic fixture approved for phase-2 benchmark",
        approved=True,
    )


def timed_match(matcher: StandardMatcher, content: bytes, mime: str) -> tuple[object, float]:
    started = time.perf_counter()
    result = matcher.match(content, mime)
    return result, (time.perf_counter() - started) * 1000.0


def main() -> None:
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="di-phase2-benchmark-") as temp:
        store = ArtifactStore(Path(temp) / "var")
        orchestrator = ParseOrchestrator(ParserRegistry([NativePdfParser()]), store)
        library = StandardLibrary(store)
        manifests = [
            register(FIXTURES / "native_text.pdf", orchestrator, library),
            register(FIXTURES / "mixed_layout.pdf", orchestrator, library),
        ]
        matcher = StandardMatcher(library)
        for manifest in manifests:
            for fingerprint in manifest.page_fingerprints:
                image = library.read_image(fingerprint.page_image_ref)
                result, elapsed = timed_match(matcher, encode_png(image), "image/png")
                rows.append(
                    {
                        "case": f"full:{fingerprint.standard_id}:{fingerprint.page_index}",
                        "expected": MatchDecision.SAFE_STANDARD_REUSE,
                        "actual": result.decision,
                        "correct_page": result.candidates[0].page_id == fingerprint.page_id,
                        "top1_score": result.top1_score,
                        "margin": result.margin,
                        "duration_ms": round(elapsed, 3),
                    }
                )
                if fingerprint.page_index == 0:
                    height, width = image.shape[:2]
                    crop = image[
                        int(height * 0.15) : int(height * 0.75),
                        int(width * 0.10) : int(width * 0.90),
                    ]
                    result, elapsed = timed_match(matcher, encode_png(crop), "image/png")
                    rows.append(
                        {
                            "case": f"crop:{fingerprint.standard_id}:{fingerprint.page_index}",
                            "expected": MatchDecision.SAFE_STANDARD_REUSE,
                            "actual": result.decision,
                            "correct_page": result.candidates[0].page_id == fingerprint.page_id,
                            "top1_score": result.top1_score,
                            "margin": result.margin,
                            "local_inliers": result.candidates[0].evidence.local_inliers,
                            "duration_ms": round(elapsed, 3),
                        }
                    )

        first_fingerprint = manifests[0].page_fingerprints[0]
        first_image = library.read_image(first_fingerprint.page_image_ref)
        first_height, first_width = first_image.shape[:2]
        first_crop = first_image[
            int(first_height * 0.15) : int(first_height * 0.75),
            int(first_width * 0.10) : int(first_width * 0.90),
        ]
        strict_matcher = StandardMatcher(
            library, high_threshold=0.999999, local_threshold=0.999999
        )
        result, elapsed = timed_match(strict_matcher, encode_png(first_crop), "image/png")
        rows.append(
            {
                "case": "strong-local-below-configured-threshold",
                "expected": MatchDecision.NO_MATCH,
                "actual": result.decision,
                "correct_page": bool(result.candidates)
                and result.candidates[0].page_id == first_fingerprint.page_id,
                "top1_score": result.top1_score,
                "margin": result.margin,
                "duration_ms": round(elapsed, 3),
            }
        )

        unknown = np.full((1200, 800, 3), 255, dtype=np.uint8)
        cv2.putText(
            unknown,
            "Completely unknown 93741",
            (40, 300),
            cv2.FONT_HERSHEY_SIMPLEX,
            2,
            (0, 0, 0),
            4,
        )
        noise = np.random.default_rng(20260802).integers(
            0, 256, (900, 700, 3), dtype=np.uint8
        )
        for name, image in [("unknown-text", unknown), ("unknown-noise", noise)]:
            result, elapsed = timed_match(matcher, encode_png(image), "image/png")
            rows.append(
                {
                    "case": name,
                    "expected": MatchDecision.NO_MATCH,
                    "actual": result.decision,
                    "correct_page": True,
                    "top1_score": result.top1_score,
                    "margin": result.margin,
                    "duration_ms": round(elapsed, 3),
                }
            )

        duplicate = register(
            FIXTURES / "native_text.pdf", orchestrator, library, filename="duplicate-name.pdf"
        )
        original = manifests[0]
        assert duplicate.standard_id != original.standard_id
        image = library.read_image(original.page_fingerprints[0].page_image_ref)
        result, elapsed = timed_match(matcher, encode_png(image), "image/png")
        rows.append(
            {
                "case": "duplicate-page-ambiguity",
                "expected": MatchDecision.AMBIGUOUS,
                "actual": result.decision,
                "correct_page": True,
                "top1_score": result.top1_score,
                "margin": result.margin,
                "duration_ms": round(elapsed, 3),
            }
        )

    for row in rows:
        row["passed"] = row["actual"] == row["expected"] and bool(row["correct_page"])
        row["expected"] = str(row["expected"])
        row["actual"] = str(row["actual"])
    passed = all(bool(row["passed"]) for row in rows)
    known = [row for row in rows if row["expected"] == str(MatchDecision.SAFE_STANDARD_REUSE)]
    negative = [row for row in rows if row["expected"] != str(MatchDecision.SAFE_STANDARD_REUSE)]
    payload = {
        "phase": 2,
        "passed": passed,
        "fixture_scope": "small synthetic regression suite; not a production accuracy claim",
        "cases": rows,
        "summary": {
            "total": len(rows),
            "passed": sum(bool(row["passed"]) for row in rows),
            "known_recall": sum(bool(row["passed"]) for row in known) / len(known),
            "negative_false_accepts": sum(
                row["actual"] == str(MatchDecision.SAFE_STANDARD_REUSE) for row in negative
            ),
            "median_duration_ms": round(
                statistics.median(float(row["duration_ms"]) for row in rows), 3
            ),
        },
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Phase 2 标准文档匹配基线",
        "",
        "> 本报告只验证项目内小型合成回归集，"
        "不代表真实行业数据上的最终准确率。",
        "",
        "| 用例 | 期望 | 实际 | 正确页 | Top-1 | 间隔 | 耗时(ms) | 通过 |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['case']} | {row['expected']} | {row['actual']} | {row['correct_page']} | "
            f"{float(row['top1_score']):.4f} | {float(row['margin']):.4f} | "
            f"{row['duration_ms']} | {'是' if row['passed'] else '否'} |"
        )
    lines.extend(
        [
            "",
            "## 门禁结果",
            "",
            f"- 用例总数：{payload['summary']['total']}；",
            f"- 通过：{payload['summary']['passed']}；",
            f"- 已知页召回：{payload['summary']['known_recall']:.2%}；",
            "- 未知/歧义页错误安全调用："
            f"{payload['summary']['negative_false_accepts']}；",
            f"- 中位匹配耗时：{payload['summary']['median_duration_ms']} ms；",
            f"- 阶段门禁：{'通过' if passed else '不通过'}。",
            "",
            "生产冻结前仍需使用真实扫描、拍照、压缩、裁剪、"
            "透视和跨版本文档扩大黄金集。",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
