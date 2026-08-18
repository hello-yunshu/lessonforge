from __future__ import annotations

import json
import sys
from pathlib import Path

from packaging.version import Version

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from document_intelligence import __version__
from document_intelligence.config import Settings
from document_intelligence.exceptions import (
    RillAccessDeniedError,
    RillFeedbackError,
    RillProtocolError,
    RillStoreCorruptError,
    RillUnavailableError,
    RillWriteDisabledError,
)
from document_intelligence.rill.client import REQUIRED_CAPABILITIES
from document_intelligence.rill.models import ACTION_ARMS, RILL_FEATURE_ORDER
from document_intelligence.rill.protocol import RILL_RUNTIME_API_VERSION_V3

OUT = ROOT / "docs" / "phase-5" / "verification.json"


def main() -> None:
    benchmark = json.loads(
        (ROOT / "docs/phase-5/benchmark_results.json").read_text(encoding="utf-8")
    )
    source_schema = json.loads(
        (ROOT / "configs/rill_observe.schema.json").read_text(encoding="utf-8")
    )
    packaged_schema = json.loads(
        (
            ROOT
            / "src/document_intelligence/defaults/rill_observe.schema.json"
        ).read_text(encoding="utf-8")
    )
    feature_schema = json.loads(
        (ROOT / "configs/rill_feature_schema.json").read_text(encoding="utf-8")
    )
    packaged_feature_schema = json.loads(
        (ROOT / "src/document_intelligence/defaults/rill_feature_schema.json").read_text(
            encoding="utf-8"
        )
    )
    license_manifest = yaml.safe_load(
        (ROOT / "configs/third_party_licenses.yaml").read_text(encoding="utf-8")
    )
    settings = Settings(parser_config=ROOT / "configs/parsers.yaml")
    taxonomy = yaml.safe_load(
        (ROOT / "configs/error_taxonomy.yaml").read_text(encoding="utf-8")
    )["categories"]
    schema_names = (
        "rill-observe-event.schema.json",
        "rill-shadow-evaluation.schema.json",
        "rill-shadow-feedback.schema.json",
        "rill-shadow-snapshot.schema.json",
    )
    checks: list[dict[str, object]] = [
        {"name": "phase5-benchmark", "passed": benchmark["passed"]},
        {
            "name": "no-production-actions",
            "passed": benchmark["summary"]["production_actions_executed"] == 0,
        },
        {"name": "version-at-least-0.5.0", "passed": Version(__version__) >= Version("0.5.0")},
        {
            "name": "rill-v3-preview-contract",
            "passed": RILL_RUNTIME_API_VERSION_V3 == 3,
        },
        {
            "name": "shadow-default-disabled",
            "passed": settings.rill_shadow_backend == "disabled"
            and not settings.enable_rill_shadow_writes,
        },
        {"name": "schema-copy-identical", "passed": source_schema == packaged_schema},
        {
            "name": "feature-schema-copy-identical",
            "passed": feature_schema == packaged_feature_schema,
        },
        {
            "name": "feature-order-frozen",
            "passed": feature_schema.get("featureOrder") == list(RILL_FEATURE_ORDER),
        },
        {
            "name": "feature-actions-frozen",
            "passed": feature_schema.get("actionArms")
            == [action.value for action in ACTION_ARMS],
        },
        {
            "name": "rill-license-recorded",
            "passed": any(
                item.get("name") == "RillML / rill-runtime"
                and item.get("license") == "MIT"
                and item.get("production_review") == "mandatory"
                for item in license_manifest.get("optional_components", [])
            ),
        },
        {
            "name": "schema-shadow-only",
            "passed": source_schema["properties"]["shadow_only"]["const"] is True,
        },
        {
            "name": "fixed-action-arm-map",
            "passed": len(ACTION_ARMS) == len(set(ACTION_ARMS)) == 9,
        },
        {
            "name": "required-capabilities-complete",
            "passed": len(REQUIRED_CAPABILITIES) == 6,
        },
        {
            "name": "rill-schemas-exported",
            "passed": all((ROOT / "docs/schema" / name).is_file() for name in schema_names),
        },
    ]
    errors = [
        RillUnavailableError,
        RillProtocolError,
        RillAccessDeniedError,
        RillWriteDisabledError,
        RillStoreCorruptError,
        RillFeedbackError,
    ]
    checks.append(
        {
            "name": "rill-errors-in-taxonomy",
            "passed": all(taxonomy.get(item.code) == item.severity for item in errors),
        }
    )
    runtime_root = ROOT / "var/rill-shadow"
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
            "name": "release-rill-state-clean",
            "passed": not runtime_files,
            "files": [str(path) for path in runtime_files],
        }
    )
    payload = {
        "phase": 5,
        "passed": all(bool(item["passed"]) for item in checks),
        "checks": checks,
    }
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
