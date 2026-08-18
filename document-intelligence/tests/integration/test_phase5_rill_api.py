from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from document_intelligence.api.main import create_app

RILL_TOKEN = "phase5-rill-token"
RILL_TOKEN_SHA256 = hashlib.sha256(RILL_TOKEN.encode()).hexdigest()
HEADERS = {"X-Rill-Token": RILL_TOKEN}


def test_rill_api_defaults_to_deny(settings) -> None:
    client = TestClient(create_app(settings))
    response = client.get("/v1/rill/shadow/inspect")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "RILL_ACCESS_DENIED"
    response = client.post("/v1/rill/shadow/evaluate", json={"parse_run_id": "run-test"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "RILL_WRITE_DISABLED"


def test_rill_shadow_api_lifecycle(settings, fixtures_dir) -> None:
    enabled = settings.model_copy(update={
        "rill_shadow_backend": "reference",
        "rill_reference_backend_allowed": True,
        "rill_access_token_sha256": RILL_TOKEN_SHA256,
        "enable_rill_shadow_writes": True,
    })
    with TestClient(create_app(enabled)) as client:
        path = fixtures_dir / "native_text.pdf"
        parsed = client.post(
            "/v1/parse",
            files={"file": (path.name, path.read_bytes(), "application/pdf")},
            data={"parser_id": "native-pdf"},
        )
        assert parsed.status_code == 200
        run_id = parsed.json()["run"]["parse_run_id"]
        structure = client.post("/v1/structure/recover", json={"run_id": run_id})
        structure_id = structure.json()["structure"]["structure_id"]

        evaluated = client.post(
            "/v1/rill/shadow/evaluate",
            headers=HEADERS,
            json={"parse_run_id": run_id, "structure_id": structure_id},
        )
        assert evaluated.status_code == 200, evaluated.text
        item = evaluated.json()["shadow_evaluation"]
        assert item["shadow_only"] is True
        assert item["no_action_executed"] is True
        action = item["rill_suggestion"]["action"]

        feedback = client.post(
            "/v1/rill/shadow/feedback",
            headers=HEADERS,
            json={
                "evaluation_id": item["evaluation_id"],
                "actual_action": action,
                "decision_correct": True,
                "error_scope": "route",
                "error_type": "none",
                "severity": "P2",
                "human_edit_seconds": 0,
                "eligible_for_training": True,
                "outcome_time_ms": 1,
            },
        )
        assert feedback.status_code == 200, feedback.text
        assert feedback.json()["shadow_feedback"]["runtime_feedback_accepted"] is True
        assert client.get("/v1/rill/shadow/replay", headers=HEADERS).status_code == 200
        inspect = client.get("/v1/rill/shadow/inspect", headers=HEADERS)
        assert inspect.json()["noProductionActions"] is True
        assert client.post("/v1/rill/shadow/snapshot", headers=HEADERS).status_code == 200
        assert client.post("/v1/rill/shadow/reset", headers=HEADERS).status_code == 200


def test_rill_get_missing_evaluation_returns_404(settings) -> None:
    enabled = settings.model_copy(update={
        "rill_access_token_sha256": RILL_TOKEN_SHA256,
    })
    with TestClient(create_app(enabled)) as client:
        response = client.get(
            "/v1/rill/shadow/evaluations/missing-evaluation", headers=HEADERS
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "shadow evaluation not found"
