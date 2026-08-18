from __future__ import annotations

import shutil

import pytest

from document_intelligence.exceptions import StructureStoreCorruptError
from document_intelligence.parsers import NativePdfParser
from document_intelligence.schema import ParseRequest
from document_intelligence.services import ArtifactStore
from document_intelligence.structure import (
    StructureRecoveryEngine,
    StructureService,
    StructureStore,
)


def test_structure_service_requires_intact_source_run(tmp_path, fixtures_dir) -> None:
    path = fixtures_dir / "native_text.pdf"
    request = ParseRequest(
        filename=path.name,
        mime_type="application/pdf",
        content=path.read_bytes(),
    )
    parsed = NativePdfParser().parse(request)
    workspace = tmp_path / "var"
    artifact_store = ArtifactStore(workspace)
    artifact_store.commit_success(request, parsed)
    service = StructureService(
        artifact_store,
        StructureStore(workspace),
        StructureRecoveryEngine(),
    )
    result = service.recover_run(parsed.run.parse_run_id)
    shutil.rmtree(workspace / "runs" / parsed.run.parse_run_id)
    with pytest.raises(StructureStoreCorruptError):
        service.get(result.structure_id)
