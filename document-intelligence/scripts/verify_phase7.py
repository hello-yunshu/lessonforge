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
    MLOpsAccessDeniedError,
    MLOpsReleaseDisabledError,
    MLOpsWriteDisabledError,
)
from document_intelligence.mlops.models import BOUNDED_AUTO_ENABLED, MLOPS_SCHEMA_VERSION

OUT = ROOT / "docs" / "phase-7" / "verification.json"


def main() -> None:
    benchmark = json.loads(
        (ROOT / "docs/phase-7/benchmark_results.json").read_text(encoding="utf-8")
    )
    settings = Settings(parser_config=ROOT / "configs/parsers.yaml")
    taxonomy = yaml.safe_load(
        (ROOT / "configs/error_taxonomy.yaml").read_text(encoding="utf-8")
    )["categories"]
    schemas = (
        "active-learning-batch.schema.json",
        "dataset-snapshot.schema.json",
        "mlflow-run-record.schema.json",
        "model-candidate.schema.json",
        "candidate-evaluation.schema.json",
        "shadow-validation.schema.json",
        "release-approval.schema.json",
        "model-alias-update.schema.json",
        "model-rollback.schema.json",
    )
    checks: list[dict[str, object]] = [
        {"name": "phase7-benchmark", "passed": benchmark["passed"]},
        {"name": "version-at-least-0.7.0", "passed": Version(__version__) >= Version("0.7.0")},
        {"name": "mlops-schema-0.7", "passed": MLOPS_SCHEMA_VERSION == "0.7"},
        {
            "name": "mlops-default-closed",
            "passed": not settings.enable_mlops_writes
            and not settings.enable_mlops_release,
        },
        {
            "name": "bounded-auto-hard-disabled",
            "passed": BOUNDED_AUTO_ENABLED is False,
        },
        {
            "name": "phase7-schemas-exported",
            "passed": all((ROOT / "docs/schema" / name).is_file() for name in schemas),
        },
        {
            "name": "production-model-not-claimed",
            "passed": benchmark["summary"]["production_model_promoted"] is False,
        },
    ]
    checks.append(
        {
            "name": "mlops-errors-in-taxonomy",
            "passed": all(
                taxonomy.get(item.code) == item.severity
                for item in (
                    MLOpsAccessDeniedError,
                    MLOpsWriteDisabledError,
                    MLOpsReleaseDisabledError,
                )
            ),
        }
    )
    runtime_root = ROOT / "var/mlops"
    runtime_files = (
        [path for path in runtime_root.rglob("*") if path.is_file() and path.name != ".gitkeep"]
        if runtime_root.exists()
        else []
    )
    checks.append(
        {
            "name": "release-mlops-state-clean",
            "passed": not runtime_files,
            "files": [str(path) for path in runtime_files],
        }
    )
    payload = {
        "phase": 7,
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
