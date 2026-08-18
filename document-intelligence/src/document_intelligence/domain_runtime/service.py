from __future__ import annotations

from document_intelligence.domain_runtime.engine import DomainRuntimeEngine
from document_intelligence.domain_runtime.models import DomainResult
from document_intelligence.domain_runtime.registry import DomainPackRegistry
from document_intelligence.domain_runtime.store import DomainResultStore
from document_intelligence.exceptions import DomainExecutionError, DomainResultStoreCorruptError
from document_intelligence.services.store import ArtifactStore
from document_intelligence.structure import StructureService


class DomainRuntimeService:
    def __init__(
        self,
        artifact_store: ArtifactStore,
        structure_service: StructureService,
        registry: DomainPackRegistry,
        result_store: DomainResultStore,
        engine: DomainRuntimeEngine,
    ) -> None:
        self.artifact_store = artifact_store
        self.structure_service = structure_service
        self.registry = registry
        self.result_store = result_store
        self.engine = engine

    def apply(
        self,
        structure_id: str,
        pack_id: str,
        version: str | None = None,
        *,
        fallback_on_error: bool = True,
    ) -> DomainResult:
        structure = self.structure_service.get(structure_id)
        parsed = self.artifact_store.read_result(structure.parse_run_id)
        pack = self.registry.load(pack_id, version)
        try:
            result = self.engine.apply(parsed.document, structure, pack)
        except Exception as exc:
            safe_code = type(exc).__name__.upper()[:127]
            safe_message = "domain adapter execution failed; inspect server diagnostics"
            if not fallback_on_error:
                raise DomainExecutionError(safe_message) from exc
            result = self.engine.fallback(
                parsed.document,
                structure,
                pack,
                code=safe_code,
                message=safe_message,
            )
        self.result_store.commit(result)
        return result

    def get(self, result_id: str) -> DomainResult:
        result = self.result_store.read(result_id)
        structure = self.structure_service.get(result.structure_id)
        if structure.semantic_digest() != result.source_structure_digest:
            raise DomainResultStoreCorruptError(
                "domain result source structure digest differs from current structure"
            )
        if (
            structure.document_id != result.document_id
            or structure.parse_run_id != result.parse_run_id
        ):
            raise DomainResultStoreCorruptError(
                "domain result source identity differs from current structure"
            )
        pack = self.registry.load(
            result.pack_id, result.pack_version, enforce_compatibility=False
        )
        if pack.content_digest != result.pack_digest:
            raise DomainResultStoreCorruptError(
                "domain result pack digest differs from installed domain pack"
            )
        parsed = self.artifact_store.read_result(result.parse_run_id)
        evidence_ids = {item.evidence_id for item in parsed.document.evidence} | {
            item.evidence_id for item in structure.evidence
        }
        element_ids = {item.element_id for item in parsed.document.elements}
        for annotation in result.annotations:
            if annotation.element_id not in element_ids:
                raise DomainResultStoreCorruptError(
                    "domain annotation references an unknown source element"
                )
            if not set(annotation.evidence_ids).issubset(evidence_ids):
                raise DomainResultStoreCorruptError(
                    "domain annotation references unknown source evidence"
                )
        for relation in result.relations:
            if not set(relation.evidence_ids).issubset(evidence_ids):
                raise DomainResultStoreCorruptError(
                    "domain relation references unknown source evidence"
                )
        return result
