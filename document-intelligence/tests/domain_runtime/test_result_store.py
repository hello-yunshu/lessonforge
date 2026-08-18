from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_intelligence.domain_runtime import DomainResultStore
from document_intelligence.exceptions import DomainResultStoreCorruptError

from .test_engine_service import build_service


def test_result_store_commit_is_idempotent_and_lists_ids(tmp_path: Path) -> None:
    service, structure, _ = build_service(tmp_path)
    result = service.apply(structure.structure_id, "education-content")
    store = DomainResultStore(tmp_path / "var")
    first = store.commit(result)
    second = store.commit(result)
    assert second == first
    assert store.list_ids() == [result.domain_result_id]


def test_result_store_rejects_same_id_with_different_semantics(tmp_path: Path) -> None:
    service, structure, _ = build_service(tmp_path)
    result = service.apply(structure.structure_id, "education-content")
    changed = result.model_copy(update={"runtime_version": "0.4.0-audit-change"})
    with pytest.raises(DomainResultStoreCorruptError, match="different semantic output"):
        service.result_store.commit(changed)


def test_result_store_detects_manifest_identity_tampering(tmp_path: Path) -> None:
    service, structure, _ = build_service(tmp_path)
    result = service.apply(structure.structure_id, "education-content")
    manifest_path = service.result_store.root / result.domain_result_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pack_id"] = "generic-document"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DomainResultStoreCorruptError, match="manifest mismatch"):
        service.result_store.read(result.domain_result_id)


def test_result_store_missing_result_is_not_found(tmp_path: Path) -> None:
    store = DomainResultStore(tmp_path / "var")
    with pytest.raises(FileNotFoundError):
        store.read("missing-result")
