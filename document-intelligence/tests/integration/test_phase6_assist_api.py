from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from document_intelligence.api.main import create_app

ASSIST_TOKEN = "phase6-assist-token"
ASSIST_TOKEN_SHA256 = hashlib.sha256(ASSIST_TOKEN.encode()).hexdigest()
HEADERS = {"X-Rill-Assist-Token": ASSIST_TOKEN}


def test_assist_api_defaults_to_deny_and_bounded_auto_is_false(settings) -> None:
    with TestClient(create_app(settings)) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["rill_assist_execution_enabled"] is False
        assert health.json()["bounded_auto_enabled"] is False
        response = client.get("/v1/rill/assist/inspect")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "RILL_ASSIST_ACCESS_DENIED"


def test_assist_execution_requires_separate_switch(settings) -> None:
    enabled = settings.model_copy(
        update={
            "rill_assist_access_token_sha256": ASSIST_TOKEN_SHA256,
            "enable_rill_assist_writes": True,
            "enable_rill_assist_execution": False,
        }
    )
    with TestClient(create_app(enabled)) as client:
        inspect = client.get("/v1/rill/assist/inspect", headers=HEADERS)
        assert inspect.status_code == 200
        assert inspect.json()["boundedAuto"] is False
        response = client.post(
            "/v1/rill/assist/execute",
            headers=HEADERS,
            json={"activation_id": "activation-test", "evaluation_id": "evaluation-test"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "RILL_ASSIST_DISABLED"
        suspend = client.post(
            "/v1/rill/assist/parsers/suspend",
            headers=HEADERS,
            json={
                "activation_id": "activation-test",
                "parser_id": "secondary-parser",
                "drift_alert_id": "drift-alert-test",
                "operator_id_hash": "0" * 64,
                "reason_code": "TEST",
                "expires_at": "2030-01-01T00:00:00Z",
            },
        )
        assert suspend.status_code == 403
        assert suspend.json()["error"]["code"] == "RILL_ASSIST_DISABLED"


def test_assist_qualification_api_records_reference_runtime_blockers(settings) -> None:
    enabled = settings.model_copy(
        update={
            "rill_shadow_backend": "reference",
            "rill_reference_backend_allowed": True,
            "rill_assist_access_token_sha256": ASSIST_TOKEN_SHA256,
            "enable_rill_assist_writes": True,
            "rill_runtime_artifact_sha256": "1" * 64,
            "rill_model_artifact_sha256": "2" * 64,
            "rill_handler_artifact_sha256": "3" * 64,
        }
    )
    with TestClient(create_app(enabled)) as client:
        qualified = client.post(
            "/v1/rill/assist/qualify",
            headers=HEADERS,
            json={"requested_actions": ["HUMAN_REVIEW"]},
        )
        assert qualified.status_code == 200, qualified.text
        report = qualified.json()["assist_qualification"]
        assert report["qualified"] is False
        assert "REFERENCE_RUNTIME_NOT_QUALIFIABLE" in report["blocking_reasons"]
        fetched = client.get(
            f"/v1/rill/assist/qualifications/{report['report_id']}",
            headers=HEADERS,
        )
        assert fetched.status_code == 200
        assert fetched.json()["assist_qualification"]["report_id"] == report["report_id"]
        activation = client.post(
            "/v1/rill/assist/activate",
            headers=HEADERS,
            json={
                "qualification_report_id": report["report_id"],
                "approver_id_hash": "4" * 64,
                "allowed_actions": ["HUMAN_REVIEW"],
                "max_executions_per_hour": 1,
                "expires_at": "2030-01-01T00:00:00Z",
            },
        )
        assert activation.status_code == 409
        assert activation.json()["error"]["code"] == "RILL_ASSIST_NOT_QUALIFIED"


def test_assist_missing_qualification_returns_404(settings) -> None:
    enabled = settings.model_copy(
        update={"rill_assist_access_token_sha256": ASSIST_TOKEN_SHA256}
    )
    with TestClient(create_app(enabled)) as client:
        response = client.get(
            "/v1/rill/assist/qualifications/missing-report", headers=HEADERS
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Assist qualification not found"
