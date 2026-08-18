from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

from document_intelligence.config import Settings
from document_intelligence.schema import ParseRequest
from document_intelligence.services import build_registry

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def main() -> int:
    parser = argparse.ArgumentParser(description="Qualify a pinned external parser gateway")
    parser.add_argument("parser_id", choices=["paddle", "opendoc", "mineru-benchmark"])
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    settings = Settings(workspace=ROOT / "var", parser_config=ROOT / "configs" / "parsers.yaml")
    registry = build_registry(settings)
    selected = registry.get(args.parser_id)
    health = selected.health()
    if not health.available:
        raise SystemExit(f"parser is not qualified for execution: {health.reason}")

    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    rows = []
    for fixture in manifest["fixtures"]:
        path = FIXTURES / fixture["file"]
        request = ParseRequest(
            filename=path.name,
            mime_type="application/pdf",
            content=path.read_bytes(),
            parser_id=args.parser_id,
        )
        durations = []
        semantic_digests = set()
        result = None
        for _ in range(args.rounds):
            started = time.perf_counter()
            result = selected.parse(request)
            durations.append((time.perf_counter() - started) * 1000)
            semantic_digests.add(result.document.semantic_digest())
        assert result is not None
        rows.append(
            {
                "fixture": path.name,
                "pages": len(result.document.pages),
                "elements": len(result.document.elements),
                "warnings": [warning.code for warning in result.run.warnings],
                "median_duration_ms": statistics.median(durations),
                "semantic_digest_reproducible": len(semantic_digests) == 1,
                "run_resource_usage": result.run.resource_usage.model_dump(mode="json")
                if result.run.resource_usage
                else None,
            }
        )
    payload = {
        "parser": health.model_dump(mode="json"),
        "environment": {
            key: bool(os.getenv(key))
            for key in [
                "DI_PADDLE_ENDPOINT",
                "DI_OPENDOC_ENDPOINT",
                "DI_MINERU_ENDPOINT",
            ]
        },
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
