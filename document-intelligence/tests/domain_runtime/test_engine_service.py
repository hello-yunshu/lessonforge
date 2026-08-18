from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_intelligence.domain_runtime import (
    DomainExecutionStatus,
    DomainPackRegistry,
    DomainResultStore,
    DomainRuntimeEngine,
    DomainRuntimeService,
)
from document_intelligence.exceptions import (
    DomainExecutionError,
    DomainPackConflictError,
    DomainResultStoreCorruptError,
)
from document_intelligence.services import ArtifactStore
from document_intelligence.structure import (
    StructureRecoveryEngine,
    StructureService,
    StructureStore,
)

from .helpers import archive_directory, build_parser_result, copy_pack


def build_service(tmp_path: Path):
    workspace = tmp_path / "var"
    request, parsed = build_parser_result()
    artifacts = ArtifactStore(workspace)
    artifacts.commit_success(request, parsed)
    structures = StructureService(
        artifacts,
        StructureStore(workspace),
        StructureRecoveryEngine(),
    )
    structure = structures.recover_run(parsed.run.parse_run_id)
    registry = DomainPackRegistry(workspace, engine_version="0.4.0")
    pack_path = copy_pack(tmp_path)
    record = registry.install_archive(archive_directory(pack_path))
    registry.activate(record.pack_id, record.version)
    service = DomainRuntimeService(
        artifacts,
        structures,
        registry,
        DomainResultStore(workspace),
        DomainRuntimeEngine(),
    )
    return service, structure, parsed


def test_domain_apply_is_isolated_and_evidence_backed(tmp_path) -> None:
    service, structure, parsed = build_service(tmp_path)
    source_digest = parsed.document.semantic_digest()
    structure_digest = structure.semantic_digest()
    result = service.apply(structure.structure_id, "education-content")
    assert result.status == DomainExecutionStatus.SUCCEEDED
    assert {item.domain_type for item in result.annotations} >= {
        "worked_example",
        "practice",
        "reflection_prompt",
        "learner_character",
        "speech",
    }
    assert {item.domain_type for item in result.relations} >= {"speaks", "practice_for"}
    assert all(item.evidence_ids for item in result.annotations)
    assert service.get(result.domain_result_id).semantic_digest() == result.semantic_digest()
    stored_document = service.artifact_store.read_result(parsed.run.parse_run_id).document
    assert stored_document.semantic_digest() == source_digest
    stored_structure = service.structure_service.get(structure.structure_id)
    assert stored_structure.semantic_digest() == structure_digest


def test_domain_failure_falls_back_without_assertions(tmp_path, monkeypatch) -> None:
    service, structure, _ = build_service(tmp_path)
    monkeypatch.setattr(
        service.engine,
        "apply",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom")),
    )
    result = service.apply(structure.structure_id, "education-content")
    assert result.status == DomainExecutionStatus.FALLBACK_GENERIC
    assert result.annotations == []
    assert result.relations == []
    assert result.failure_message == "domain adapter execution failed; inspect server diagnostics"
    assert "boom" not in result.failure_message
    stored_structure = service.structure_service.get(structure.structure_id)
    assert stored_structure.structure_id == structure.structure_id


def test_domain_result_tampering_is_detected(tmp_path) -> None:
    service, structure, _ = build_service(tmp_path)
    result = service.apply(structure.structure_id, "education-content")
    path = service.result_store.root / result.domain_result_id / "result.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["metrics"]["annotations"] = 0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DomainResultStoreCorruptError):
        service.get(result.domain_result_id)


def test_referenced_pack_cannot_be_uninstalled(tmp_path) -> None:
    service, structure, _ = build_service(tmp_path)
    result = service.apply(structure.structure_id, "education-content")
    service.registry.deactivate(result.pack_id)
    with pytest.raises(DomainPackConflictError):
        service.registry.uninstall(result.pack_id, result.pack_version)


def test_domain_failure_without_fallback_is_wrapped_and_sanitized(tmp_path, monkeypatch) -> None:
    service, structure, _ = build_service(tmp_path)
    monkeypatch.setattr(
        service.engine,
        "apply",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("secret-path=/srv/private")),
    )
    with pytest.raises(DomainExecutionError, match="inspect server diagnostics") as caught:
        service.apply(
            structure.structure_id,
            "education-content",
            fallback_on_error=False,
        )
    assert "secret-path" not in str(caught.value)


def test_historical_domain_result_remains_readable_after_engine_upgrade(tmp_path) -> None:
    service, structure, _ = build_service(tmp_path)
    result = service.apply(structure.structure_id, "education-content")
    upgraded_registry = DomainPackRegistry(tmp_path / "var", engine_version="1.0.0")
    upgraded_service = DomainRuntimeService(
        service.artifact_store,
        service.structure_service,
        upgraded_registry,
        service.result_store,
        DomainRuntimeEngine(),
    )
    loaded = upgraded_service.get(result.domain_result_id)
    assert loaded.semantic_digest() == result.semantic_digest()
