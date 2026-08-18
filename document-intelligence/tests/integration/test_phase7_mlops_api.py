from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from document_intelligence.api.main import create_app

TOKEN = "phase7-mlops-token"
TOKEN_SHA256 = hashlib.sha256(TOKEN.encode()).hexdigest()
HEADERS = {"X-MLOps-Token": TOKEN}


def test_mlops_api_defaults_to_deny_and_release_is_separate(settings) -> None:
    with TestClient(create_app(settings)) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["mlops_writes_enabled"] is False
        assert health.json()["mlops_release_enabled"] is False
        denied = client.get("/v1/mlops/inspect")
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "MLOPS_ACCESS_DENIED"

    enabled = settings.model_copy(
        update={
            "mlops_access_token_sha256": TOKEN_SHA256,
            "enable_mlops_writes": True,
            "enable_mlops_release": False,
        }
    )
    with TestClient(create_app(enabled)) as client:
        inspect = client.get("/v1/mlops/inspect", headers=HEADERS)
        assert inspect.status_code == 200
        assert inspect.json()["boundedAuto"] is False
        blocked = client.post(
            "/v1/mlops/promote/shadow",
            headers=HEADERS,
            json={
                "candidate_id": "candidate-missing",
                "evaluation_report_id": "evaluation-missing",
                "approval_id": "approval-missing",
                "operator_id_hash": "0" * 64,
                "reason_code": "TEST",
            },
        )
        assert blocked.status_code == 403
        assert blocked.json()["error"]["code"] == "MLOPS_RELEASE_DISABLED"


def test_dataset_snapshot_api_is_hash_only_and_immutable(settings) -> None:
    enabled = settings.model_copy(
        update={
            "mlops_access_token_sha256": TOKEN_SHA256,
            "enable_mlops_writes": True,
        }
    )
    payload = {
        "role": "train",
        "dataset_name": "training-set",
        "dvc_repo_revision": "a" * 40,
        "dvc_data_hash": "1" * 64,
        "manifest_sha256": "2" * 64,
        "schema_sha256": "3" * 64,
        "source_commit_sha": "b" * 40,
        "record_count": 10,
        "file_count": 2,
    }
    with TestClient(create_app(enabled)) as client:
        first = client.post("/v1/mlops/datasets", headers=HEADERS, json=payload)
        assert first.status_code == 200, first.text
        second = client.post("/v1/mlops/datasets", headers=HEADERS, json=payload)
        assert second.status_code == 200
        assert first.json() == second.json()
        assert first.json()["dataset_snapshot"]["immutable"] is True
