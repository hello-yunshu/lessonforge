from __future__ import annotations

from typing import TYPE_CHECKING

from document_intelligence.exceptions import StructureStoreCorruptError

if TYPE_CHECKING:
    from document_intelligence.services.store import ArtifactStore
from document_intelligence.structure.engine import StructureRecoveryEngine
from document_intelligence.structure.models import StructureResult
from document_intelligence.structure.store import StructureStore


class StructureService:
    def __init__(
        self,
        artifact_store: "ArtifactStore",
        structure_store: StructureStore,
        engine: StructureRecoveryEngine,
    ) -> None:
        self.artifact_store = artifact_store
        self.structure_store = structure_store
        self.engine = engine

    def recover_run(self, run_id: str) -> StructureResult:
        parsed = self.artifact_store.read_result(run_id)
        result = self.engine.recover(parsed.document)
        self.structure_store.commit(result)
        return result

    def get(self, structure_id: str) -> StructureResult:
        result = self.structure_store.read(structure_id)
        try:
            parsed = self.artifact_store.read_result(result.parse_run_id)
        except FileNotFoundError as exc:
            raise StructureStoreCorruptError(
                "structure source parse run is missing"
            ) from exc
        if parsed.document.document_id != result.document_id:
            raise StructureStoreCorruptError(
                "structure document identity differs from source parse run"
            )
        if parsed.document.semantic_digest() != result.source_semantic_digest:
            raise StructureStoreCorruptError(
                "structure source semantic digest differs from parse run"
            )
        return result

    def list_ids(self) -> list[str]:
        return self.structure_store.list_ids()
