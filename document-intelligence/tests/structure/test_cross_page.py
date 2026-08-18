from __future__ import annotations

from document_intelligence.schema import BaseType
from document_intelligence.structure import StructureRecoveryEngine

from .helpers import build_document


def test_cross_page_continuation_requires_boundary_and_nonterminal_text() -> None:
    document = build_document(
        [
            [
                (
                    "left",
                    BaseType.TEXT,
                    (0.10, 0.80, 0.90, 0.96),
                    "This sentence continues,",
                )
            ],
            [
                (
                    "right",
                    BaseType.TEXT,
                    (0.10, 0.04, 0.90, 0.18),
                    "with the next page.",
                )
            ],
        ]
    )
    result = StructureRecoveryEngine().recover(document)
    relation = next(item for item in result.relations if item.type == "continues_on")
    assert relation.source_id == "left"
    assert relation.target_id == "right"
    assert result.metrics.cross_page_relations == 1


def test_terminal_text_does_not_force_cross_page_relation() -> None:
    document = build_document(
        [
            [("left", BaseType.TEXT, (0.10, 0.80, 0.90, 0.96), "Complete.")],
            [("right", BaseType.TEXT, (0.10, 0.04, 0.90, 0.18), "New text")],
        ]
    )
    result = StructureRecoveryEngine().recover(document)
    assert not any(item.type == "continues_on" for item in result.relations)
