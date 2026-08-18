from __future__ import annotations

from document_intelligence.schema import BaseType
from document_intelligence.structure import StructureRecoveryEngine

from .helpers import build_document


def test_heading_hierarchy_and_scope_are_recovered() -> None:
    document = build_document(
        [
            [
                ("h1", BaseType.HEADING, (0.05, 0.05, 0.95, 0.13), "Top"),
                ("p1", BaseType.TEXT, (0.05, 0.16, 0.95, 0.21), "Intro"),
                ("h2", BaseType.HEADING, (0.05, 0.28, 0.70, 0.32), "Child A"),
                ("p2", BaseType.TEXT, (0.05, 0.35, 0.95, 0.40), "A body"),
                ("h3", BaseType.HEADING, (0.05, 0.50, 0.70, 0.54), "Child B"),
                ("p3", BaseType.TEXT, (0.05, 0.57, 0.95, 0.62), "B body"),
            ]
        ]
    )
    result = StructureRecoveryEngine().recover(document)
    assert [node.level for node in result.outline] == [1, 2, 2]
    assert result.outline[0].parent_node_id is None
    assert result.outline[1].parent_node_id == result.outline[0].node_id
    assert result.outline[2].parent_node_id == result.outline[0].node_id
    assert result.outline[1].content_element_ids == ["p2"]


def test_visual_caption_relation_has_two_source_evidence_items() -> None:
    document = build_document(
        [
            [
                ("image", BaseType.IMAGE, (0.10, 0.15, 0.85, 0.60), None),
                (
                    "caption",
                    BaseType.TEXT,
                    (0.15, 0.61, 0.80, 0.65),
                    "Figure 1 Example",
                ),
            ]
        ]
    )
    result = StructureRecoveryEngine().recover(document)
    relation = next(item for item in result.relations if item.type == "caption_of")
    assert relation.source_id == "caption"
    assert relation.target_id == "image"
    assert len(relation.evidence_ids) == 2
    assert all(item in {e.evidence_id for e in result.evidence} for item in relation.evidence_ids)
    assert any(group.kind.value == "visual_with_caption" for group in result.groups)


def test_nearby_body_text_without_caption_geometry_is_not_linked() -> None:
    document = build_document(
        [
            [
                ("image", BaseType.IMAGE, (0.10, 0.15, 0.85, 0.60), None),
                (
                    "body",
                    BaseType.TEXT,
                    (0.05, 0.61, 0.95, 0.66),
                    "Ordinary body text below the visual",
                ),
            ]
        ]
    )
    result = StructureRecoveryEngine().recover(document)
    assert not any(item.type == "caption_of" for item in result.relations)
