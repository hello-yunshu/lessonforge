from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_intelligence.freeze import FreezeManifest, FreezeService, build_manifest
from document_intelligence.freeze.models import canonical_digest
from document_intelligence.freeze.registry import AUDIT_RECORDS, PERMISSION_BOUNDARIES
from document_intelligence.rill.assist_models import BOUNDED_AUTO_ENABLED


def test_packaged_manifest_matches_live_contracts() -> None:
    service = FreezeService()
    expected = service.load_manifest()
    actual = build_manifest()
    verification = service.verify()
    assert expected == actual
    assert verification.compatible is True
    assert verification.exact_match is True
    assert verification.differences == []
    assert expected.project_version == "1.0.0"
    assert expected.production_qualified is False
    assert BOUNDED_AUTO_ENABLED is False


def test_manifest_rejects_tampering(tmp_path: Path) -> None:
    original = FreezeService().load_manifest().model_dump(mode="json")
    original["contracts"][0]["payload"]["immutable"] = False
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        FreezeService(path).load_manifest()


def test_manifest_digest_covers_all_contracts() -> None:
    manifest = FreezeService().load_manifest()
    payload = manifest.model_dump(mode="json", exclude={"manifest_digest"})
    assert canonical_digest(payload) == manifest.manifest_digest
    assert len(manifest.contracts) == 10
    assert {item.kind.value for item in manifest.contracts} == {
        "core_schema",
        "parser_sdk",
        "domain_pack_sdk",
        "rill_protocol",
        "rest_api",
        "version_semantics",
        "permission_boundary",
        "release_gates",
        "rollback_behavior",
        "audit_log_format",
    }


def test_audit_registry_identifiers_are_real_or_digest_based() -> None:
    for _, _, model, id_field in AUDIT_RECORDS:
        assert id_field in model.model_fields


def test_permission_boundaries_are_closed_by_default() -> None:
    from document_intelligence.config import Settings

    settings = Settings()
    for flag, token in PERMISSION_BOUNDARIES:
        assert getattr(settings, flag) is False
        if token is not None:
            assert getattr(settings, token) is None


def test_self_consistent_replacement_manifest_fails_trust_anchor(tmp_path: Path) -> None:
    payload = FreezeService().load_manifest().model_dump(mode="json")
    payload["production_blockers"].append("self-consistent-tamper")
    payload["production_blockers"].sort()
    payload["manifest_digest"] = canonical_digest(
        {key: value for key, value in payload.items() if key != "manifest_digest"}
    )
    path = tmp_path / "replacement.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="trust anchor"):
        FreezeService(path).load_manifest()
