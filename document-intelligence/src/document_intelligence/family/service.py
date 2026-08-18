from __future__ import annotations

from document_intelligence.domain_runtime import DomainPackRegistry
from document_intelligence.exceptions import FamilyDetectionStoreCorruptError
from document_intelligence.family.detector import (
    DocumentFamilyDetector,
    family_profile_digest,
)
from document_intelligence.family.models import FamilyDetectionResult
from document_intelligence.family.store import FamilyDetectionStore
from document_intelligence.services.store import ArtifactStore
from document_intelligence.structure import StructureService


class DocumentFamilyService:
    def __init__(
        self,
        artifact_store: ArtifactStore,
        structure_service: StructureService,
        registry: DomainPackRegistry,
        store: FamilyDetectionStore,
        detector: DocumentFamilyDetector,
        *,
        max_profiles: int = 64,
    ) -> None:
        self.artifact_store = artifact_store
        self.structure_service = structure_service
        self.registry = registry
        self.store = store
        self.detector = detector
        self.max_profiles = max_profiles

    def detect(self, structure_id: str) -> FamilyDetectionResult:
        structure = self.structure_service.get(structure_id)
        parsed = self.artifact_store.read_result(structure.parse_run_id)
        packs = []
        for record in self.registry.list_records():
            if not record.active:
                continue
            pack = self.registry.load(record.pack_id, record.version)
            if pack.family is not None:
                packs.append(pack)
        if len(packs) > self.max_profiles:
            raise ValueError("active family profile count exceeds configured limit")
        result = self.detector.detect(parsed.document, structure, packs)
        self.store.commit(result)
        return result

    def get(self, detection_id: str) -> FamilyDetectionResult:
        result = self.store.read(detection_id)
        structure = self.structure_service.get(result.structure_id)
        parsed = self.artifact_store.read_result(result.parse_run_id)
        if structure.semantic_digest() != result.source_structure_digest:
            raise FamilyDetectionStoreCorruptError(
                "family detection source structure digest differs from current structure"
            )
        if parsed.document.semantic_digest() != result.source_document_digest:
            raise FamilyDetectionStoreCorruptError(
                "family detection source document digest differs from current parse run"
            )
        if (
            structure.document_id != result.document_id
            or structure.parse_run_id != result.parse_run_id
            or parsed.document.document_id != result.document_id
        ):
            raise FamilyDetectionStoreCorruptError(
                "family detection source identity differs from current artifacts"
            )
        for candidate in result.candidates:
            pack = self.registry.load(
                candidate.pack_id, candidate.pack_version, enforce_compatibility=False
            )
            if (
                pack.content_digest != candidate.pack_digest
                or pack.family is None
                or family_profile_digest(pack.family) != candidate.profile_digest
            ):
                raise FamilyDetectionStoreCorruptError(
                    "family detection candidate pack differs from installed source"
                )
        return result
