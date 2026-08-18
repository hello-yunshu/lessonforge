from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_intelligence.domain_runtime import DomainPackRegistry
from document_intelligence.exceptions import (
    DomainPackConflictError,
    FamilyDetectionStoreCorruptError,
)
from document_intelligence.family import (
    DocumentFamilyDetector,
    DocumentFamilyService,
    FamilyDecision,
    FamilyDetectionStore,
)
from document_intelligence.services import ArtifactStore
from document_intelligence.structure import (
    StructureRecoveryEngine,
    StructureService,
    StructureStore,
)
from tests.domain_runtime.helpers import archive_directory, build_parser_result, copy_pack


def build_family_service(tmp_path: Path) -> tuple[DocumentFamilyService, str, DomainPackRegistry]:
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
    registry = DomainPackRegistry(workspace, engine_version="0.8.0")
    pack = copy_pack(tmp_path, "education-content")
    record = registry.install_archive(archive_directory(pack))
    registry.activate(record.pack_id, record.version)
    service = DocumentFamilyService(
        artifacts,
        structures,
        registry,
        FamilyDetectionStore(workspace),
        DocumentFamilyDetector(),
    )
    return service, structure.structure_id, registry


def test_family_detection_is_advisory_persistent_and_evidence_backed(tmp_path: Path) -> None:
    service, structure_id, _ = build_family_service(tmp_path)
    result = service.detect(structure_id)
    assert result.decision == FamilyDecision.CANDIDATE
    assert result.selected_pack_id == "education-content"
    assert result.no_domain_action_executed is True
    assert result.candidates[0].positive_matches
    assert all(match.evidence_ids for match in result.candidates[0].positive_matches)
    assert service.get(result.detection_id).semantic_digest() == result.semantic_digest()
    repeated = service.detect(structure_id)
    assert repeated.detection_id == result.detection_id
    assert repeated.semantic_digest() == result.semantic_digest()


def test_family_detection_tampering_is_detected(tmp_path: Path) -> None:
    service, structure_id, _ = build_family_service(tmp_path)
    result = service.detect(structure_id)
    result_path = service.store.root / result.detection_id / "result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["decision"] = "no_match"
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(FamilyDetectionStoreCorruptError):
        service.get(result.detection_id)


def test_family_detection_reference_blocks_pack_uninstall(tmp_path: Path) -> None:
    service, structure_id, registry = build_family_service(tmp_path)
    result = service.detect(structure_id)
    assert result.selected_pack_version is not None
    registry.deactivate("education-content")
    with pytest.raises(DomainPackConflictError, match="family detections"):
        registry.uninstall("education-content", result.selected_pack_version)


def test_family_store_rechecks_namespace_symlink(tmp_path: Path) -> None:
    store = FamilyDetectionStore(tmp_path / "var")
    original = store.root
    original.rmdir()
    target = tmp_path / "outside"
    target.mkdir()
    original.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        store.list_ids()
