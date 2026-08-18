from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from document_intelligence.api.main import create_app

DOMAIN_TOKEN = "phase8-domain-token"
FAMILY_TOKEN = "phase8-family-token"
DOMAIN_HEADERS = {"X-Domain-Pack-Token": DOMAIN_TOKEN}
FAMILY_HEADERS = {"X-Family-Detection-Token": FAMILY_TOKEN}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def test_builtin_install_and_advisory_family_detection(
    settings, fixtures_dir: Path
) -> None:
    enabled = settings.model_copy(
        update={
            "enable_domain_pack_writes": True,
            "domain_pack_access_token_sha256": digest(DOMAIN_TOKEN),
            "enable_family_detection_writes": True,
            "family_detection_access_token_sha256": digest(FAMILY_TOKEN),
        }
    )
    client = TestClient(create_app(enabled))
    catalog = client.get("/v1/domain-packs/builtin", headers=DOMAIN_HEADERS)
    assert catalog.status_code == 200
    assert len(catalog.json()["domain_packs"]) == 6
    installed = client.post(
        "/v1/domain-packs/builtin/academic-paper/install?activate=true",
        headers=DOMAIN_HEADERS,
    )
    assert installed.status_code == 200, installed.text
    assert installed.json()["domain_pack"]["active"] is True

    path = fixtures_dir / "native_text.pdf"
    parsed = client.post(
        "/v1/parse",
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
        data={"parser_id": "native-pdf"},
    )
    assert parsed.status_code == 200
    run_id = parsed.json()["run"]["parse_run_id"]
    recovered = client.post("/v1/structure/recover", json={"run_id": run_id})
    structure_id = recovered.json()["structure"]["structure_id"]
    detected = client.post(
        "/v1/family/detect",
        headers=FAMILY_HEADERS,
        json={"structure_id": structure_id},
    )
    assert detected.status_code == 200, detected.text
    result = detected.json()["family_detection"]
    assert result["no_domain_action_executed"] is True
    fetched = client.get(
        f"/v1/family-detections/{result['detection_id']}", headers=FAMILY_HEADERS
    )
    assert fetched.status_code == 200


def test_family_and_builtin_management_default_to_deny(settings) -> None:
    client = TestClient(create_app(settings))
    assert client.get("/v1/domain-packs/builtin").status_code == 403
    denied = client.post("/v1/family/detect", json={"structure_id": "structure_safe"})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FAMILY_DETECTION_WRITE_DISABLED"
