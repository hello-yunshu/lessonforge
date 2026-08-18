from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from document_intelligence.exceptions import StructureStoreCorruptError
from document_intelligence.schema import BaseType
from document_intelligence.structure import StructureRecoveryEngine, StructureResult, StructureStore

from .helpers import build_document


def test_structure_output_is_semantically_deterministic() -> None:
    document = build_document(
        [[("body", BaseType.TEXT, (0.10, 0.20, 0.90, 0.30), "Body")]]
    )
    engine = StructureRecoveryEngine()
    first = engine.recover(document)
    second = engine.recover(document)
    assert first.structure_id == second.structure_id
    assert first.semantic_digest() == second.semantic_digest()


def test_structure_model_rejects_invalid_content_partition() -> None:
    document = build_document(
        [[("body", BaseType.TEXT, (0.10, 0.20, 0.90, 0.30), "Body")]]
    )
    payload = StructureRecoveryEngine().recover(document).model_dump(mode="python")
    payload["content_reading_order"] = []
    with pytest.raises(ValidationError):
        StructureResult.model_validate(payload)


def test_structure_store_detects_result_tampering(tmp_path) -> None:
    document = build_document(
        [[("body", BaseType.TEXT, (0.10, 0.20, 0.90, 0.30), "Body")]]
    )
    result = StructureRecoveryEngine().recover(document)
    store = StructureStore(tmp_path / "var")
    directory = store.commit(result)
    loaded = store.read(result.structure_id)
    assert loaded.semantic_digest() == result.semantic_digest()
    path = directory / "result.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["metrics"]["consistency_score"] = 0.1
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(StructureStoreCorruptError):
        store.read(result.structure_id)
