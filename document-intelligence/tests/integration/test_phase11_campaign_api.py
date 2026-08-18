from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from document_intelligence.api.main import create_app
from document_intelligence.campaign import QualificationCampaignService
from document_intelligence.config import Settings

TOKEN = "phase11-token"
H = "a" * 64


def settings(tmp_path: Path, *, writes: bool) -> Settings:
    return Settings(
        workspace=tmp_path,
        enable_qualification_campaign_writes=writes,
        qualification_campaign_access_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),
        production_minimum_domains=1,
        production_minimum_gold_documents=1,
        production_minimum_challenge_documents=1,
        production_minimum_soak_hours=1,
        production_minimum_scale_concurrency=1,
        production_minimum_scale_documents=1,
        production_minimum_pilot_days=1,
        production_minimum_pilot_documents=1,
        production_minimum_pilot_expert_reviews=1,
    )


def payload(app: object) -> dict[str, object]:
    service: QualificationCampaignService = app.state.campaign_service
    request = service.default_request(
        campaign_name="api-campaign",
        source_commit_sha="a" * 40,
        environment_sha256=H,
        policy_sha256=service.production.policy.digest(),
        created_by_id_hash=H,
    ).model_copy(update={"external_data_authorized": True})
    return request.model_dump(mode="json")


def test_campaign_api_is_default_deny_and_authenticated(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "closed", writes=False))
    with TestClient(app) as client:
        response = client.post(
            "/v1/qualification-campaigns",
            headers={"X-DI-Access-Token": TOKEN},
            json=payload(app),
        )
        assert response.status_code == 403

    app = create_app(settings(tmp_path / "open", writes=True))
    with TestClient(app) as client:
        assert client.get("/v1/qualification-campaigns/inspect").status_code == 403
        created = client.post(
            "/v1/qualification-campaigns",
            headers={"X-DI-Access-Token": TOKEN},
            json=payload(app),
        )
        assert created.status_code == 200
        campaign_id = created.json()["campaign"]["campaign_id"]
        started = client.post(
            f"/v1/qualification-campaigns/{campaign_id}/start",
            headers={"X-DI-Access-Token": TOKEN},
            json={"actor_id_hash": H},
        )
        assert started.status_code == 200
        inspected = client.get(
            "/v1/qualification-campaigns/inspect",
            headers={"X-DI-Access-Token": TOKEN},
        )
        assert inspected.json()["campaignCount"] == 1
        assert inspected.json()["automaticReleaseAuthorized"] is False


def test_campaign_bundle_import_requires_production_write_permission(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "import-closed", writes=True))
    with TestClient(app) as client:
        response = client.post(
            "/v1/qualification-campaigns/bundles/import",
            headers={
                "X-DI-Access-Token": TOKEN,
                "X-DI-Production-Token": TOKEN,
            },
            files={"file": ("bundle.zip", b"not-a-zip", "application/zip")},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == (
            "PRODUCTION_QUALIFICATION_WRITE_DISABLED"
        )
