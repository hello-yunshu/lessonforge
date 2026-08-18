from __future__ import annotations

from fastapi.testclient import TestClient

from document_intelligence.api.main import create_app


def test_structure_recovery_and_fetch_through_api(settings, fixtures_dir) -> None:
    client = TestClient(create_app(settings))
    path = fixtures_dir / "native_text.pdf"
    parsed = client.post(
        "/v1/parse",
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
        data={"parser_id": "native-pdf"},
    )
    assert parsed.status_code == 200, parsed.text
    run_id = parsed.json()["run"]["parse_run_id"]
    recovered = client.post("/v1/structure/recover", json={"run_id": run_id})
    assert recovered.status_code == 200, recovered.text
    structure = recovered.json()["structure"]
    assert structure["parse_run_id"] == run_id
    assert structure["metrics"]["reading_order_coverage"] == 1.0
    fetched = client.get(f"/v1/structures/{structure['structure_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["structure"]["structure_id"] == structure["structure_id"]


def test_structure_recovery_rejects_unsafe_run_id(settings) -> None:
    client = TestClient(create_app(settings))
    response = client.post("/v1/structure/recover", json={"run_id": "../escape"})
    assert response.status_code == 422
