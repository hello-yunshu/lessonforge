from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from document_intelligence.api.main import create_app
from tests.domain_runtime.helpers import archive_directory, copy_pack

DOMAIN_TOKEN = "phase4-domain-token"
DOMAIN_TOKEN_SHA256 = hashlib.sha256(DOMAIN_TOKEN.encode()).hexdigest()
DOMAIN_HEADERS = {"X-Domain-Pack-Token": DOMAIN_TOKEN}


def test_domain_pack_management_defaults_to_deny(settings, tmp_path: Path) -> None:
    client = TestClient(create_app(settings))
    response = client.get("/v1/domain-packs")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DOMAIN_PACK_ACCESS_DENIED"

    pack = copy_pack(tmp_path)
    response = client.post(
        "/v1/domain-packs/install",
        files={"file": ("pack.zip", archive_directory(pack), "application/zip")},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DOMAIN_PACK_WRITE_DISABLED"


def test_domain_pack_install_apply_review_and_reference_guard(
    settings, fixtures_dir: Path, tmp_path: Path
) -> None:
    enabled = settings.model_copy(
        update={
            "enable_domain_pack_writes": True,
            "domain_pack_access_token_sha256": DOMAIN_TOKEN_SHA256,
        }
    )
    client = TestClient(create_app(enabled))
    pack = copy_pack(tmp_path, "generic-document")
    installed = client.post(
        "/v1/domain-packs/install",
        headers=DOMAIN_HEADERS,
        files={"file": ("generic.zip", archive_directory(pack), "application/zip")},
    )
    assert installed.status_code == 200, installed.text
    record = installed.json()["domain_pack"]

    activated = client.post(
        f"/v1/domain-packs/{record['pack_id']}/{record['version']}/activate",
        headers=DOMAIN_HEADERS,
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["domain_pack"]["active"] is True
    listed = client.get("/v1/domain-packs", headers=DOMAIN_HEADERS)
    assert listed.status_code == 200
    assert listed.json()["domain_packs"][0]["pack_id"] == "generic-document"

    path = fixtures_dir / "native_text.pdf"
    parsed = client.post(
        "/v1/parse",
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
        data={"parser_id": "native-pdf"},
    )
    assert parsed.status_code == 200, parsed.text
    run_id = parsed.json()["run"]["parse_run_id"]
    recovered = client.post("/v1/structure/recover", json={"run_id": run_id})
    assert recovered.status_code == 200
    structure_id = recovered.json()["structure"]["structure_id"]

    applied = client.post(
        "/v1/domain/apply",
        json={"structure_id": structure_id, "pack_id": "generic-document"},
    )
    assert applied.status_code == 200, applied.text
    result = applied.json()["domain_result"]
    assert result["status"] == "succeeded"
    assert result["annotations"]
    fetched = client.get(f"/v1/domain-results/{result['domain_result_id']}")
    assert fetched.status_code == 200

    exported = client.post(
        f"/v1/domain-results/{result['domain_result_id']}/review/export",
        headers=DOMAIN_HEADERS,
    )
    assert exported.status_code == 200, exported.text
    review_export = exported.json()["review_export"]
    first = next(
        obj
        for task in review_export["tasks"]
        for obj in task["objects"]
    )
    submitted = client.post(
        "/v1/domain-reviews",
        headers=DOMAIN_HEADERS,
        json={
            "adapter": "labelu-json-v1",
            "export_id": review_export["export_id"],
            "domain_result_id": result["domain_result_id"],
            "source_domain_digest": review_export["source_domain_digest"],
            "reviewer": "api-reviewer",
            "review_level": "reviewer",
            "reason": "verified through API",
            "objects": [{"element_id": first["element_id"], "labels": [first["label"]]}],
            "relations": [],
        },
    )
    assert submitted.status_code == 200, submitted.text

    deactivated = client.post(
        "/v1/domain-packs/generic-document/deactivate", headers=DOMAIN_HEADERS
    )
    assert deactivated.status_code == 200
    blocked = client.delete(
        f"/v1/domain-packs/generic-document/{record['version']}",
        headers=DOMAIN_HEADERS,
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "DOMAIN_PACK_CONFLICT"


def test_domain_pack_management_rejects_wrong_token(settings) -> None:
    enabled = settings.model_copy(
        update={
            "enable_domain_pack_writes": True,
            "domain_pack_access_token_sha256": DOMAIN_TOKEN_SHA256,
        }
    )
    client = TestClient(create_app(enabled))
    response = client.get(
        "/v1/domain-packs", headers={"X-Domain-Pack-Token": "wrong"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "DOMAIN_PACK_ACCESS_DENIED"
