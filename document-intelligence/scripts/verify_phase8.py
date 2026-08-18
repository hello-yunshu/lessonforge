from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from document_intelligence import __version__
from document_intelligence.domain_regression import CrossDomainRegressionReport
from document_intelligence.domain_runtime import DomainPackRegistry, DomainRuntimeEngine
from document_intelligence.mlops.models import BOUNDED_AUTO_ENABLED
from document_intelligence.schema import ParsedDocument

OUT = ROOT / "docs" / "phase-8" / "verification.json"
EXPECTED_CORE_SCHEMA_SHA256 = (
    "9e8be89228dd68a4f65aec8832bc89b75ff29217c9f7a5842d4f93666bacb09a"
)
EXPECTED_BUILTINS = {
    "generic-document",
    "education-content",
    "examination-paper",
    "academic-paper",
    "legal-contract",
    "technical-manual",
}


def main() -> None:
    benchmark = CrossDomainRegressionReport.model_validate_json(
        (ROOT / "docs/phase-8/CROSS_DOMAIN_BENCHMARK.json").read_text(
            encoding="utf-8"
        )
    )
    schema_digest = hashlib.sha256(
        json.dumps(
            ParsedDocument.model_json_schema(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    with tempfile.TemporaryDirectory(prefix="di-phase8-registry-") as temp_value:
        registry = DomainPackRegistry(
            Path(temp_value) / "var",
            engine_version=DomainRuntimeEngine.runtime_version,
        )
        builtins = registry.list_builtin_records()
    schemas = (
        "document-family-profile.schema.json",
        "family-detection-result.schema.json",
        "cross-domain-regression-report.schema.json",
    )
    checks: list[dict[str, object]] = [
        {"name": "phase8-benchmark", "passed": benchmark.passed},
        {"name": "version-at-least-0.8.0", "passed": Version(__version__) >= Version("0.8.0")},
        {
            "name": "domain-runtime-at-least-0.8.0",
            "passed": Version(DomainRuntimeEngine.runtime_version) >= Version("0.8.0"),
        },
        {
            "name": "core-schema-unchanged",
            "passed": schema_digest == EXPECTED_CORE_SCHEMA_SHA256,
            "actual": schema_digest,
        },
        {
            "name": "builtin-domain-pack-set",
            "passed": {item.pack_id for item in builtins} == EXPECTED_BUILTINS,
            "packs": sorted(item.pack_id for item in builtins),
        },
        {
            "name": "five-family-profiles",
            "passed": sum(item.has_family_profile for item in builtins) == 5,
        },
        {
            "name": "phase8-schemas-exported",
            "passed": all((ROOT / "docs/schema" / name).is_file() for name in schemas),
        },
        {
            "name": "family-detection-advisory",
            "passed": all(
                case.detected_pack_id == case.expected_pack_id for case in benchmark.cases
            ),
        },
        {
            "name": "domain-results-isolated",
            "passed": all(case.isolated_results for case in benchmark.cases),
        },
        {
            "name": "evidence-gates-preserved",
            "passed": all(case.evidence_complete for case in benchmark.cases),
        },
        {
            "name": "bounded-auto-hard-disabled",
            "passed": BOUNDED_AUTO_ENABLED is False and benchmark.bounded_auto is False,
        },
    ]
    runtime_root = ROOT / "var"
    guarded_namespaces = {
        "family-detections",
        "domain-results",
        "domain-reviews",
        "rill-shadow",
        "rill-assist",
        "mlops",
    }
    runtime_files = [
        path
        for namespace in guarded_namespaces
        for path in (runtime_root / namespace).rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    ]
    checks.append(
        {
            "name": "release-runtime-state-clean",
            "passed": not runtime_files,
            "files": [str(path) for path in runtime_files],
        }
    )
    payload = {
        "phase": 8,
        "passed": all(bool(item["passed"]) for item in checks),
        "checks": checks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
