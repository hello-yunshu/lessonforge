from __future__ import annotations

from document_intelligence.schema import BaseType
from document_intelligence.structure import StructureRecoveryEngine

from .helpers import build_document


def test_two_column_reading_order_is_column_major() -> None:
    document = build_document(
        [
            [
                ("heading", BaseType.HEADING, (0.05, 0.02, 0.95, 0.08), "Heading"),
                ("left_1", BaseType.TEXT, (0.05, 0.14, 0.43, 0.20), "Left one"),
                ("right_1", BaseType.TEXT, (0.57, 0.12, 0.95, 0.18), "Right one"),
                ("left_2", BaseType.TEXT, (0.05, 0.25, 0.43, 0.31), "Left two"),
                ("right_2", BaseType.TEXT, (0.57, 0.23, 0.95, 0.29), "Right two"),
            ]
        ]
    )
    result = StructureRecoveryEngine().recover(document)
    assert result.content_reading_order == [
        "heading",
        "left_1",
        "left_2",
        "right_1",
        "right_2",
    ]
    assert result.metrics.reading_order_coverage == 1.0


def test_repeated_headers_and_page_numbers_are_excluded_from_content() -> None:
    pages = []
    for index in range(3):
        pages.append(
            [
                (
                    f"header_{index}",
                    BaseType.TEXT,
                    (0.10, 0.02, 0.90, 0.06),
                    "Shared Header",
                ),
                (
                    f"body_{index}",
                    BaseType.TEXT,
                    (0.10, 0.20, 0.90, 0.30),
                    f"Body {index}",
                ),
                (
                    f"page_number_{index}",
                    BaseType.TEXT,
                    (0.45, 0.93, 0.55, 0.97),
                    str(index + 1),
                ),
            ]
        )
    result = StructureRecoveryEngine().recover(build_document(pages))
    assert result.content_reading_order == ["body_0", "body_1", "body_2"]
    assert set(result.excluded_margin_element_ids) == {
        "header_0",
        "header_1",
        "header_2",
        "page_number_0",
        "page_number_1",
        "page_number_2",
    }
    assert any(group.kind.value == "repeated_margin" for group in result.groups)


def test_sparse_side_by_side_blocks_are_left_to_right() -> None:
    document = build_document(
        [
            [
                ("right", BaseType.TEXT, (0.60, 0.10, 0.95, 0.20), "Right"),
                ("left", BaseType.TEXT, (0.05, 0.11, 0.40, 0.21), "Left"),
            ]
        ]
    )
    result = StructureRecoveryEngine().recover(document)
    assert result.content_reading_order == ["left", "right"]
