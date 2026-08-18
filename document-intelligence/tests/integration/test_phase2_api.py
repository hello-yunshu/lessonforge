from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from document_intelligence.api.main import create_app

STANDARD_TOKEN = "phase2-test-token"
STANDARD_TOKEN_SHA256 = hashlib.sha256(STANDARD_TOKEN.encode()).hexdigest()
STANDARD_HEADERS = {"X-Standard-Token": STANDARD_TOKEN}


def test_standard_registration_is_disabled_by_default(settings, fixtures_dir) -> None:
    client = TestClient(create_app(settings))
    path = fixtures_dir / "native_text.pdf"
    parsed = client.post(
        "/v1/parse",
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
        data={"parser_id": "native-pdf"},
    )
    assert parsed.status_code == 200
    run_id = parsed.json()["run"]["parse_run_id"]
    response = client.post(
        "/v1/standard/register",
        json={
            "run_id": run_id,
            "reviewer": "reviewer",
            "approval_note": "approved fixture",
            "approved": True,
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "STANDARD_WRITE_DISABLED"


def test_register_and_match_through_api(settings, fixtures_dir) -> None:
    enabled = settings.model_copy(
        update={
            "enable_standard_writes": True,
            "standard_access_token_sha256": STANDARD_TOKEN_SHA256,
        }
    )
    client = TestClient(create_app(enabled))
    path = fixtures_dir / "native_text.pdf"
    parsed = client.post(
        "/v1/parse",
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
        data={"parser_id": "native-pdf"},
    )
    run_id = parsed.json()["run"]["parse_run_id"]
    registered = client.post(
        "/v1/standard/register",
        headers=STANDARD_HEADERS,
        json={
            "run_id": run_id,
            "reviewer": "reviewer",
            "approval_note": "approved fixture",
            "approved": True,
        },
    )
    assert registered.status_code == 200, registered.text
    match = client.post(
        "/v1/match",
        headers=STANDARD_HEADERS,
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
        data={"page_index": "0", "include_standard": "true"},
    )
    assert match.status_code == 200, match.text
    payload = match.json()
    assert payload["match"]["decision"] == "safe_standard_reuse"
    assert payload["standard_document"]["source"]["sha256"] == (
        parsed.json()["document"]["source"]["sha256"]
    )


def test_match_invalid_pdf_page_returns_stable_400(settings, fixtures_dir) -> None:
    client = TestClient(create_app(settings))
    path = fixtures_dir / "native_text.pdf"
    response = client.post(
        "/v1/match",
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
        data={"page_index": "99"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MATCH_INPUT_INVALID"


def test_standard_registration_rejects_unsafe_run_id_at_schema_boundary(settings) -> None:
    enabled = settings.model_copy(
        update={
            "enable_standard_writes": True,
            "standard_access_token_sha256": STANDARD_TOKEN_SHA256,
        }
    )
    client = TestClient(create_app(enabled))
    response = client.post(
        "/v1/standard/register",
        json={
            "run_id": "../escape",
            "reviewer": "reviewer",
            "approval_note": "invalid",
            "approved": True,
        },
    )
    assert response.status_code == 422


def test_standard_library_defaults_to_denying_reads(settings) -> None:
    client = TestClient(create_app(settings))
    response = client.get("/v1/standard")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "STANDARD_ACCESS_DENIED"


def test_standard_registration_requires_valid_access_token(settings) -> None:
    enabled = settings.model_copy(
        update={
            "enable_standard_writes": True,
            "standard_access_token_sha256": STANDARD_TOKEN_SHA256,
        }
    )
    client = TestClient(create_app(enabled))
    response = client.post(
        "/v1/standard/register",
        headers={"X-Standard-Token": "wrong-token"},
        json={
            "run_id": "run_missing",
            "reviewer": "reviewer",
            "approval_note": "should not reach store",
            "approved": True,
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "STANDARD_ACCESS_DENIED"


def test_match_standard_payload_requires_access_token(settings, fixtures_dir) -> None:
    client = TestClient(create_app(settings))
    path = fixtures_dir / "native_text.pdf"
    response = client.post(
        "/v1/match",
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
        data={"page_index": "0", "include_standard": "true"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "STANDARD_ACCESS_DENIED"
