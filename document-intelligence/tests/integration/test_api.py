from __future__ import annotations

from fastapi.testclient import TestClient

from document_intelligence.api.main import create_app


def test_health_and_parser_listing(settings) -> None:
    client = TestClient(create_app(settings))
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["schema_version"] == "1.1"
    assert health.json()["structure_engine_version"] == "0.3.0"
    assert health.json()["domain_runtime_version"] == "1.0.0"
    parsers = client.get("/v1/parsers")
    assert parsers.status_code == 200
    payload = parsers.json()["parsers"]
    assert any(item["parser_id"] == "native-pdf" and item["available"] for item in payload)
    assert any(item["parser_id"] == "paddle" and not item["available"] for item in payload)


def test_parse_and_fetch_run(settings, fixtures_dir) -> None:
    client = TestClient(create_app(settings))
    path = fixtures_dir / "native_text.pdf"
    response = client.post(
        "/v1/parse",
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
        data={"parser_id": "native-pdf", "include_document": "true"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    run_id = payload["run"]["parse_run_id"]
    assert payload["document"]["source"]["filename"] == path.name
    fetched = client.get(f"/v1/runs/{run_id}")
    assert fetched.status_code == 200
    assert fetched.json()["run"]["parse_run_id"] == run_id


def test_api_rejects_unsupported_input(settings) -> None:
    client = TestClient(create_app(settings))
    response = client.post(
        "/v1/parse",
        files={"file": ("x.bin", b"unsupported", "application/octet-stream")},
        data={"parser_id": "auto"},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "INPUT_UNSUPPORTED"
