from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from document_intelligence import __version__
from document_intelligence.api.main import create_app
from document_intelligence.config import Settings
from document_intelligence.domain_runtime import DomainPackRegistry, DomainRuntimeEngine
from document_intelligence.freeze import (
    FROZEN_API_OPERATIONS,
    FreezeBenchmarkReport,
    FreezeService,
)
from document_intelligence.freeze.registry import AUDIT_RECORDS, PERMISSION_BOUNDARIES
from document_intelligence.rill.assist_models import BOUNDED_AUTO_ENABLED

OUT = ROOT / "docs/phase-9/verification.json"


def main() -> None:
    benchmark = FreezeBenchmarkReport.model_validate_json(
        (ROOT / "docs/phase-9/benchmark_results.json").read_text(encoding="utf-8")
    )
    service = FreezeService()
    manifest = service.load_manifest()
    verification = service.verify()
    checks: list[dict[str, object]] = [
        {"name": "phase9-benchmark", "passed": benchmark.passed},
        {
            "name": "version-in-frozen-1.x-range",
            "passed": Version("1.0.0") <= Version(__version__) < Version("2.0.0"),
        },
        {
            "name": "domain-runtime-1.0.0",
            "passed": DomainRuntimeEngine.runtime_version == "1.0.0",
        },
        {"name": "freeze-exact-match", "passed": verification.exact_match},
        {
            "name": "ten-contract-kinds",
            "passed": len(manifest.contracts) == 10
            and len({item.kind for item in manifest.contracts}) == 10,
        },
        {
            "name": "engineering-not-production",
            "passed": manifest.status == "engineering_frozen"
            and manifest.production_qualified is False,
        },
        {
            "name": "bounded-auto-hard-disabled",
            "passed": BOUNDED_AUTO_ENABLED is False,
        },
        {
            "name": "freeze-copies-identical",
            "passed": (
                ROOT / "docs/phase-9/FROZEN_CONTRACTS_V1.json"
            ).read_bytes()
            == (
                ROOT / "src/document_intelligence/defaults/frozen_contracts_v1.json"
            ).read_bytes(),
        },
        {
            "name": "phase9-schemas-exported",
            "passed": all(
                (ROOT / "docs/schema" / name).is_file()
                for name in (
                    "freeze-manifest.schema.json",
                    "freeze-verification.schema.json",
                    "freeze-benchmark-report.schema.json",
                    "review-record.schema.json",
                )
            ),
        },
        {
            "name": "audit-identities-valid",
            "passed": all(
                id_field in model.model_fields
                for _, _, model, id_field in AUDIT_RECORDS
            ),
        },
    ]
    defaults = Settings()
    checks.append(
        {
            "name": "permission-defaults-closed",
            "passed": all(
                getattr(defaults, flag) is False for flag, _ in PERMISSION_BOUNDARIES
            )
            and all(
                token is None or getattr(defaults, token) is None
                for _, token in PERMISSION_BOUNDARIES
            ),
        }
    )
    with tempfile.TemporaryDirectory(prefix="di-phase9-verify-") as temp_value:
        settings = Settings(workspace=Path(temp_value) / "var")
        app = create_app(settings)
        actual = {
            (method, route.path)
            for route in app.routes
            for method in getattr(route, "methods", set())
            if route.path == "/healthz" or route.path.startswith("/v1/")
        }
        checks.append(
            {
                "name": "rest-api-frozen-operations-present",
                "passed": set(FROZEN_API_OPERATIONS).issubset(actual),
            }
        )
        registry = DomainPackRegistry(
            settings.workspace,
            engine_version=DomainRuntimeEngine.runtime_version,
        )
        records = registry.list_builtin_records()
        compatible = True
        try:
            for record in records:
                installed = registry.install_builtin(record.pack_id)
                registry.load(installed.pack_id, installed.version)
        except Exception:
            compatible = False
        checks.append(
            {
                "name": "six-domain-packs-compatible",
                "passed": compatible and len(records) == 6,
            }
        )
    runtime_root = ROOT / "var"
    guarded_namespaces = {
        "runs",
        "raw",
        "sources",
        "assets",
        "standard",
        "structures",
        "domain-packs",
        "domain-results",
        "domain-reviews",
        "family-detections",
        "rill-shadow",
        "rill-assist",
        "mlops",
        "production-qualification",
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
            "files": [str(path.relative_to(ROOT)) for path in runtime_files],
        }
    )
    payload = {
        "phase": 9,
        "passed": all(bool(item["passed"]) for item in checks),
        "manifest_digest": manifest.manifest_digest,
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
