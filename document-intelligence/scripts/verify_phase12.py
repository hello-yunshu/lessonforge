from __future__ import annotations

import json
from pathlib import Path

from document_intelligence import __version__
from document_intelligence.config import Settings
from document_intelligence.freeze import FreezeService

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase-12" / "verification.json"


def main() -> None:
    benchmark = json.loads(
        (ROOT / "docs" / "phase-12" / "benchmark_results.json").read_text(
            encoding="utf-8"
        )
    )
    settings = Settings()
    freeze = FreezeService().verify()
    checks = [
        {"name": "release-candidate-version", "passed": __version__ == "1.0.3rc1"},
        {"name": "phase12-benchmark", "passed": benchmark["passed"]},
        {"name": "one-x-contracts-preserved", "passed": freeze.compatible},
        {
            "name": "development-backward-compatible",
            "passed": settings.deployment_profile == "development",
        },
        {
            "name": "production-qualification-not-bundled",
            "passed": not any(
                path.is_file() and path.name != ".gitkeep"
                for path in (ROOT / "var" / "production-qualification").rglob("*")
            ),
        },
        {
            "name": "security-runtime-clean",
            "passed": not any(
                path.is_file() and path.name != ".gitkeep"
                for path in (ROOT / "var" / "security").rglob("*")
            ),
        },
        {
            "name": "release-documents-present",
            "passed": all(
                (ROOT / name).is_file()
                for name in ("LICENSE", "NOTICE", "SECURITY.md", "SUPPORT.md")
            ),
        },
        {
            "name": "current-package-target",
            "passed": "build_release_candidate.py"
            in (ROOT / "Makefile").read_text(encoding="utf-8"),
        },
        {
            "name": "dockerignore-present",
            "passed": (ROOT / ".dockerignore").is_file(),
        },
        {
            "name": "bounded-auto-remains-disabled",
            "passed": benchmark["production_qualified"] is False,
        },
    ]
    payload = {
        "phase": 12,
        "passed": all(bool(item["passed"]) for item in checks),
        "checks": checks,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
