from __future__ import annotations

import json
import tempfile
from pathlib import Path

import yaml

from document_intelligence.exceptions import (
    StructureRecoveryError,
    StructureStoreCorruptError,
)
from document_intelligence.parsers import NativePdfParser
from document_intelligence.schema import ParseRequest
from document_intelligence.services import ArtifactStore
from document_intelligence.structure import (
    STRUCTURE_SCHEMA_VERSION,
    StructureRecoveryEngine,
    StructureService,
    StructureStore,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase-3" / "verification.json"


def main() -> None:
    checks: list[dict[str, object]] = []
    fixture = ROOT / "tests" / "fixtures" / "native_text.pdf"
    content = fixture.read_bytes()
    parser = NativePdfParser()
    request = ParseRequest(
        filename=fixture.name,
        mime_type="application/pdf",
        content=content,
    )
    parsed = parser.parse(request)

    with tempfile.TemporaryDirectory(prefix="di-phase3-verify-") as temp:
        workspace = Path(temp) / "var"
        artifact_store = ArtifactStore(workspace)
        artifact_store.commit_success(request, parsed)
        service = StructureService(
            artifact_store,
            StructureStore(workspace),
            StructureRecoveryEngine(),
        )
        first = service.recover_run(parsed.run.parse_run_id)
        second = service.recover_run(parsed.run.parse_run_id)
        checks.append(
            {
                "name": "structure-semantic-determinism",
                "passed": first.structure_id == second.structure_id
                and first.semantic_digest() == second.semantic_digest(),
            }
        )
        loaded = service.get(first.structure_id)
        checks.append(
            {
                "name": "structure-store-roundtrip-integrity",
                "passed": loaded.semantic_digest() == first.semantic_digest(),
            }
        )
        checks.append(
            {
                "name": "reading-order-complete",
                "passed": first.metrics.reading_order_coverage == 1.0
                and len(first.reading_order) == len(parsed.document.elements),
            }
        )
        checks.append(
            {
                "name": "all-relations-have-evidence",
                "passed": first.metrics.relation_evidence_coverage == 1.0
                and all(item.evidence_ids for item in first.relations),
            }
        )
        checks.append(
            {
                "name": "source-semantic-digest-bound",
                "passed": first.source_semantic_digest
                == parsed.document.semantic_digest(),
            }
        )

    benchmark = json.loads(
        (ROOT / "docs" / "phase-3" / "benchmark_results.json").read_text(
            encoding="utf-8"
        )
    )
    checks.append({"name": "phase3-benchmark-gate", "passed": benchmark["passed"]})
    checks.append(
        {
            "name": "synthetic-relation-false-positive-gate",
            "passed": benchmark["summary"]["false_positive_relations"] == 0,
        }
    )
    checks.append(
        {
            "name": "structure-schema-exported",
            "passed": (
                ROOT / "docs" / "schema" / "structure-result.schema.json"
            ).is_file()
            and STRUCTURE_SCHEMA_VERSION == "1.0",
        }
    )

    rill_schema = json.loads(
        (ROOT / "configs" / "rill_observe.schema.json").read_text(
            encoding="utf-8"
        )
    )
    signals_ref = rill_schema["properties"]["signals"]["$ref"].split("/")[-1]
    signal_properties = rill_schema["$defs"][signals_ref]["properties"]
    checks.append(
        {
            "name": "rill-structure-signals-shadow-only",
            "passed": rill_schema["properties"]["shadow_only"]["const"] is True
            and "structure" in signal_properties,
        }
    )

    structure_files = [
        path
        for path in (ROOT / "var" / "structures").rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    ]
    checks.append(
        {"name": "release-structure-store-clean", "passed": not structure_files}
    )
    checks.append(
        {
            "name": "runtime-structure-namespace-present",
            "passed": (ROOT / "var" / "structures" / ".gitkeep").is_file(),
        }
    )

    cli_test = (ROOT / "tests" / "integration" / "test_cli.py").read_text(
        encoding="utf-8"
    )
    checks.append(
        {
            "name": "cli-test-has-no-release-absolute-config-path",
            "passed": "/mnt/data/AI分析教材" not in cli_test,
        }
    )

    taxonomy = yaml.safe_load(
        (ROOT / "configs" / "error_taxonomy.yaml").read_text(encoding="utf-8")
    )
    categories = taxonomy.get("categories", {})
    checks.append(
        {
            "name": "phase3-errors-in-taxonomy",
            "passed": categories.get(StructureRecoveryError.code)
            == StructureRecoveryError.severity
            and categories.get(StructureStoreCorruptError.code)
            == StructureStoreCorruptError.severity,
        }
    )

    payload = {
        "phase": 3,
        "passed": all(bool(check["passed"]) for check in checks),
        "checks": checks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
