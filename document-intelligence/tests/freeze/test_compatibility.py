from __future__ import annotations

import json
from pathlib import Path

from document_intelligence.freeze import FreezeService


def test_missing_contract_is_reported(tmp_path: Path, monkeypatch) -> None:
    payload = FreezeService().load_manifest().model_dump(mode="json")
    payload["contracts"][0]["contract_id"] = "audit-log-v2"
    from document_intelligence.freeze.models import canonical_digest

    payload["manifest_digest"] = canonical_digest(
        {key: value for key, value in payload.items() if key != "manifest_digest"}
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        "document_intelligence.freeze.service.FROZEN_MANIFEST_V1_DIGEST",
        payload["manifest_digest"],
    )
    verification = FreezeService(path).verify()
    assert verification.compatible is False
    assert verification.exact_match is False
    assert {item.reason for item in verification.differences} == {
        "missing contract", "unexpected contract"
    }


def test_contract_digest_change_is_reported(tmp_path: Path, monkeypatch) -> None:
    payload = FreezeService().load_manifest().model_dump(mode="json")
    contract = payload["contracts"][0]
    contract["payload"]["canonical_json"] = "changed"
    from document_intelligence.freeze.models import canonical_digest

    contract["digest"] = canonical_digest(contract["payload"])
    payload["manifest_digest"] = canonical_digest(
        {key: value for key, value in payload.items() if key != "manifest_digest"}
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        "document_intelligence.freeze.service.FROZEN_MANIFEST_V1_DIGEST",
        payload["manifest_digest"],
    )
    verification = FreezeService(path).verify()
    assert verification.compatible is False
    assert any(item.reason == "contract digest changed" for item in verification.differences)
