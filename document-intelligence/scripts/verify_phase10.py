from __future__ import annotations

import json
import tempfile
from pathlib import Path

from packaging.version import Version

from document_intelligence import __version__
from document_intelligence.api.main import create_app
from document_intelligence.config import Settings
from document_intelligence.freeze import FreezeService
from document_intelligence.production import BOUNDED_AUTO_ENABLED
from document_intelligence.services import build_production_qualification_service

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/phase-10/verification.json"
REQUIRED_ROUTES = {
    ("POST", "/v1/production/evidence/datasets"),
    ("POST", "/v1/production/evidence/parsers"),
    ("POST", "/v1/production/evidence/scale"),
    ("POST", "/v1/production/evidence/supply-chain"),
    ("POST", "/v1/production/evidence/licenses"),
    ("POST", "/v1/production/evidence/pilots"),
    ("POST", "/v1/production/qualify"),
    ("GET", "/v1/production/reports/{report_id}"),
    ("GET", "/v1/production/inspect"),
}


def main() -> None:
    benchmark = json.loads(
        (ROOT / "docs/phase-10/benchmark_results.json").read_text(encoding="utf-8")
    )
    defaults = Settings()
    checks: list[dict[str, object]] = [
        {"name": "phase10-benchmark", "passed": benchmark["passed"]},
        {
            "name": "version-is-phase10-compatible",
            "passed": Version("1.0.1") <= Version(__version__) < Version("2.0.0"),
        },
        {
            "name": "v1-freeze-remains-compatible",
            "passed": FreezeService().verify().compatible,
        },
        {
            "name": "production-writes-default-closed",
            "passed": (
                defaults.enable_production_qualification_writes is False
                and defaults.production_qualification_access_token_sha256 is None
            ),
        },
        {"name": "bounded-auto-hard-disabled", "passed": BOUNDED_AUTO_ENABLED is False},
        {
            "name": "production-schemas-exported",
            "passed": all(
                (ROOT / "docs/schema" / name).is_file()
                for name in (
                    "production-dataset-evidence.schema.json",
                    "production-parser-evidence.schema.json",
                    "production-scale-evidence.schema.json",
                    "production-supply-chain-evidence.schema.json",
                    "production-license-evidence.schema.json",
                    "production-pilot-evidence.schema.json",
                    "production-qualification-report.schema.json",
                )
            ),
        },
    ]
    with tempfile.TemporaryDirectory(prefix="di-phase10-verify-") as value:
        settings = Settings(workspace=Path(value) / "var")
        service = build_production_qualification_service(settings)
        checks.append(
            {
                "name": "new-workspace-has-no-qualification",
                "passed": service.inspect()["qualifiedReportCount"] == 0,
            }
        )
        app = create_app(settings)
        actual = {
            (method, route.path)
            for route in app.routes
            for method in getattr(route, "methods", set())
        }
        checks.append(
            {
                "name": "production-rest-operations-present",
                "passed": REQUIRED_ROUTES.issubset(actual),
            }
        )
    runtime = ROOT / "var" / "production-qualification"
    records = [
        path
        for path in runtime.rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    ]
    checks.append(
        {
            "name": "release-has-no-production-evidence",
            "passed": not records,
            "files": [str(path.relative_to(ROOT)) for path in records],
        }
    )
    payload = {
        "phase": 10,
        "passed": all(bool(item["passed"]) for item in checks),
        "production_qualified": False,
        "checks": checks,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
