from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from document_intelligence import __version__
from document_intelligence.config import Settings
from document_intelligence.exceptions import (
    RillAssistAccessDeniedError,
    RillAssistDisabledError,
    RillAssistExecutionError,
    RillAssistQualificationError,
)
from document_intelligence.rill.assist_models import (
    ASSIST_SCHEMA_VERSION,
    BOUNDED_AUTO_ENABLED,
    TIER1_ACTIONS,
)

OUT = ROOT / "docs" / "phase-6" / "verification.json"


def main() -> None:
    benchmark = json.loads(
        (ROOT / "docs/phase-6/benchmark_results.json").read_text(encoding="utf-8")
    )
    source_policy = yaml.safe_load(
        (ROOT / "configs/rill_assist_policy.yaml").read_text(encoding="utf-8")
    )
    packaged_policy = yaml.safe_load(
        (ROOT / "src/document_intelligence/defaults/rill_assist_policy.yaml").read_text(
            encoding="utf-8"
        )
    )
    taxonomy = yaml.safe_load(
        (ROOT / "configs/error_taxonomy.yaml").read_text(encoding="utf-8")
    )["categories"]
    settings = Settings(parser_config=ROOT / "configs/parsers.yaml")
    schema_names = (
        "rill-assist-attestation.schema.json",
        "rill-assist-qualification.schema.json",
        "rill-assist-activation.schema.json",
        "rill-assist-execution.schema.json",
        "rill-assist-revocation.schema.json",
        "rill-assist-parser-suspension.schema.json",
        "rill-assist-parser-resume.schema.json",
    )
    checks: list[dict[str, object]] = [
        {"name": "phase6-benchmark", "passed": benchmark["passed"]},
        {"name": "version-at-least-0.6.0", "passed": Version(__version__) >= Version("0.6.0")},
        {"name": "assist-schema-0.6", "passed": ASSIST_SCHEMA_VERSION == "0.6"},
        {
            "name": "assist-default-disabled",
            "passed": not settings.enable_rill_assist_writes
            and not settings.enable_rill_assist_execution,
        },
        {
            "name": "bounded-auto-hard-disabled",
            "passed": BOUNDED_AUTO_ENABLED is False
            and source_policy.get("bounded_auto") is False,
        },
        {"name": "assist-policy-copy-identical", "passed": source_policy == packaged_policy},
        {
            "name": "tier1-action-policy-frozen",
            "passed": source_policy.get("allowed_actions")
            == [action.value for action in TIER1_ACTIONS],
        },
        {
            "name": "artifact-digests-required-by-policy",
            "passed": source_policy.get("required_qualification", {}).get(
                "fixed_runtime_model_handler_digests"
            )
            is True,
        },
        {
            "name": "runtime-inspect-artifact-attestation-required",
            "passed": source_policy.get("required_qualification", {}).get(
                "runtime_inspect_artifact_attestation"
            )
            is True,
        },
        {
            "name": "native-fallback-not-suspendable",
            "passed": source_policy.get("parser_circuit_breaker", {}).get(
                "native_pdf_fallback_suspendable"
            )
            is False,
        },
        {
            "name": "assist-schemas-exported",
            "passed": all((ROOT / "docs/schema" / name).is_file() for name in schema_names),
        },
        {
            "name": "no-production-assist-claim",
            "passed": benchmark["summary"]["production_assist_activated"] is False,
        },
    ]
    errors = (
        RillAssistAccessDeniedError,
        RillAssistDisabledError,
        RillAssistQualificationError,
        RillAssistExecutionError,
    )
    checks.append(
        {
            "name": "assist-errors-in-taxonomy",
            "passed": all(taxonomy.get(item.code) == item.severity for item in errors),
        }
    )
    runtime_root = ROOT / "var/rill-assist"
    runtime_files = (
        [
            path
            for path in runtime_root.rglob("*")
            if path.is_file() and path.name != ".gitkeep"
        ]
        if runtime_root.exists()
        else []
    )
    checks.append(
        {
            "name": "release-assist-state-clean",
            "passed": not runtime_files,
            "files": [str(path) for path in runtime_files],
        }
    )
    payload = {
        "phase": 6,
        "passed": all(bool(item["passed"]) for item in checks),
        "checks": checks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
