from __future__ import annotations

import json
import tempfile
from pathlib import Path

from packaging.version import Version

from document_intelligence import __version__
from document_intelligence.api.main import create_app
from document_intelligence.campaign import QualificationCampaignService
from document_intelligence.config import Settings
from document_intelligence.freeze import FreezeService
from document_intelligence.services import (
    build_production_qualification_service,
    build_qualification_campaign_service,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/phase-11/verification.json"
REQUIRED_ROUTES = {
    ("POST", "/v1/qualification-campaigns"),
    ("GET", "/v1/qualification-campaigns/inspect"),
    ("GET", "/v1/qualification-campaigns/{campaign_id}"),
    ("POST", "/v1/qualification-campaigns/{campaign_id}/start"),
    ("POST", "/v1/qualification-campaigns/{campaign_id}/steps/{step_id}/claim"),
    ("POST", "/v1/qualification-campaigns/{campaign_id}/steps/{step_id}/checkpoint"),
    ("POST", "/v1/qualification-campaigns/{campaign_id}/steps/{step_id}/evidence"),
    ("POST", "/v1/qualification-campaigns/{campaign_id}/steps/{step_id}/complete"),
    ("POST", "/v1/qualification-campaigns/{campaign_id}/finalize"),
    ("POST", "/v1/qualification-campaigns/{campaign_id}/bundle"),
    ("POST", "/v1/qualification-campaigns/bundles/import"),
}


def main() -> None:
    version = Version(__version__)
    checks: list[dict[str, object]] = [
        {
            "name": "version-is-phase11-compatible",
            "passed": Version("1.0.2") <= version < Version("2.0.0"),
            "version": __version__,
        },
        {
            "name": "one-x-freeze-remains-compatible",
            "passed": FreezeService().verify().compatible,
        },
        {
            "name": "campaign-schemas-exported",
            "passed": all(
                (ROOT / "docs/schema" / name).is_file()
                for name in (
                    "qualification-campaign-manifest.schema.json",
                    "qualification-campaign-event.schema.json",
                    "qualification-campaign-snapshot.schema.json",
                    "qualification-campaign-bundle.schema.json",
                )
            ),
        },
    ]
    with tempfile.TemporaryDirectory(prefix="di-phase11-verify-") as value:
        settings = Settings(workspace=Path(value) / "var")
        production = build_production_qualification_service(settings)
        service: QualificationCampaignService = build_qualification_campaign_service(
            settings, production_service=production
        )
        inspect = service.inspect()
        checks.extend(
            [
                {
                    "name": "campaign-writes-default-disabled",
                    "passed": settings.enable_qualification_campaign_writes is False,
                },
                {
                    "name": "new-workspace-has-no-campaigns",
                    "passed": inspect["campaignCount"] == 0,
                },
                {
                    "name": "campaign-cannot-authorize-release",
                    "passed": inspect["automaticReleaseAuthorized"] is False
                    and inspect["boundedAuto"] is False,
                },
            ]
        )
        app = create_app(settings)
        actual = {
            (method, route.path)
            for route in app.routes
            for method in getattr(route, "methods", set())
        }
        checks.append(
            {
                "name": "campaign-rest-operations-present",
                "passed": REQUIRED_ROUTES.issubset(actual),
            }
        )
    runtime = ROOT / "var" / "qualification-campaigns"
    records = [
        path
        for path in runtime.rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    ] if runtime.exists() else []
    checks.append(
        {
            "name": "release-has-no-campaign-runtime-records",
            "passed": not records,
            "files": [str(path.relative_to(ROOT)) for path in records],
        }
    )
    payload = {
        "phase": 11,
        "passed": all(bool(item["passed"]) for item in checks),
        "production_qualified": False,
        "automatic_release_authorized": False,
        "bounded_auto": False,
        "checks": checks,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
