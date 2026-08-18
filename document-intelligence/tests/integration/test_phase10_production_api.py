from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from document_intelligence.api.main import create_app
from document_intelligence.config import Settings


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def test_production_api_is_default_deny(tmp_path: Path) -> None:
    app = create_app(Settings(workspace=tmp_path / "var"))
    with TestClient(app) as client:
        response = client.get("/v1/production/inspect")
        assert response.status_code == 403
        health = client.get("/healthz").json()
        assert health["production_qualification_writes_enabled"] is False
        assert health["production_qualified"] is False


def test_production_api_records_blocked_evidence_with_token(tmp_path: Path) -> None:
    token = "production-secret"
    app = create_app(
        Settings(
            workspace=tmp_path / "var",
            enable_production_qualification_writes=True,
            production_qualification_access_token_sha256=digest(token),
            production_minimum_domains=1,
            production_minimum_gold_documents=1,
        )
    )
    payload = {
        "dataset_name": "synthetic-only",
        "role": "gold",
        "origin": "synthetic",
        "domain_families": ["education-content"],
        "document_count": 1,
        "page_count": 1,
        "modalities": ["native-pdf"],
        "edge_cases": ["none"],
        "manifest_sha256": "a" * 64,
        "schema_sha256": "b" * 64,
        "content_snapshot_sha256": "c" * 64,
        "evidence_sha256": "d" * 64,
        "expert_approved": True,
        "approver_id_hash": "e" * 64,
        "privacy_reviewed": True,
        "license_reviewed": True,
    }
    with TestClient(app) as client:
        denied = client.post("/v1/production/evidence/datasets", json=payload)
        assert denied.status_code == 403
        response = client.post(
            "/v1/production/evidence/datasets",
            json=payload,
            headers={"X-Production-Qualification-Token": token},
        )
        assert response.status_code == 200
        evidence = response.json()["dataset_qualification_evidence"]
        assert evidence["passed"] is False
        assert "DATASET_NOT_REAL" in evidence["blocking_reasons"]
        inspect = client.get(
            "/v1/production/inspect",
            headers={"X-Production-Qualification-Token": token},
        ).json()
        assert inspect["datasetEvidenceCount"] == 1
        assert inspect["qualifiedReportCount"] == 0
