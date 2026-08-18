from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from document_intelligence.schema import (
    BaseType,
    BoundingBox,
    Confidence,
    Element,
    ElementContent,
    Evidence,
    EvidenceKind,
    Page,
    ParsedDocument,
    SourceDescriptor,
)
from document_intelligence.structure import StructureRecoveryEngine

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase-3" / "benchmark_results.json"

ElementSpec = tuple[str, BaseType, tuple[float, float, float, float], str | None]


def build_document(page_specs: Sequence[Sequence[ElementSpec]]) -> ParsedDocument:
    source_hash = hashlib.sha256(repr(page_specs).encode()).hexdigest()
    run_id = f"run_{source_hash[:20]}"
    pages: list[Page] = []
    elements: list[Element] = []
    evidence: list[Evidence] = []
    for page_index, specs in enumerate(page_specs):
        page_id = f"page_{page_index}"
        element_ids: list[str] = []
        for element_id, base_type, coords, text in specs:
            bbox = BoundingBox(x1=coords[0], y1=coords[1], x2=coords[2], y2=coords[3])
            evidence_id = f"ev_{element_id}"
            evidence.append(
                Evidence(
                    evidence_id=evidence_id,
                    kind=EvidenceKind.MODEL_PREDICTION,
                    producer="phase3-benchmark",
                    producer_version="1",
                    model_digest="0" * 64,
                    parse_run_id=run_id,
                    source_page_id=page_id,
                    bbox=bbox,
                )
            )
            elements.append(
                Element(
                    element_id=element_id,
                    page_id=page_id,
                    base_type=base_type,
                    subtype=f"benchmark_{base_type.value}",
                    bbox=bbox,
                    content=ElementContent(text=text),
                    confidence=Confidence(overall=0.95),
                    evidence_ids=[evidence_id],
                )
            )
            element_ids.append(element_id)
        pages.append(
            Page(
                page_id=page_id,
                index=page_index,
                width=1000,
                height=1000,
                element_ids=element_ids,
            )
        )
    return ParsedDocument(
        document_id=f"doc_{source_hash[:20]}",
        source=SourceDescriptor(
            filename="benchmark.pdf",
            sha256=source_hash,
            mime_type="application/pdf",
            size_bytes=1,
        ),
        pages=pages,
        elements=elements,
        evidence=evidence,
        parse_run_id=run_id,
    )


def main() -> None:
    engine = StructureRecoveryEngine()
    cases: list[dict[str, object]] = []

    two_column = build_document(
        [
            [
                ("h", BaseType.HEADING, (0.05, 0.02, 0.95, 0.08), "Heading"),
                ("l1", BaseType.TEXT, (0.05, 0.14, 0.43, 0.20), "Left one"),
                ("r1", BaseType.TEXT, (0.57, 0.12, 0.95, 0.18), "Right one"),
                ("l2", BaseType.TEXT, (0.05, 0.25, 0.43, 0.31), "Left two"),
                ("r2", BaseType.TEXT, (0.57, 0.23, 0.95, 0.29), "Right two"),
            ]
        ]
    )
    result = engine.recover(two_column)
    expected_order = ["h", "l1", "l2", "r1", "r2"]
    cases.append(
        {
            "name": "two-column-reading-order",
            "passed": result.content_reading_order == expected_order,
            "actual": result.content_reading_order,
            "expected": expected_order,
        }
    )

    outline_doc = build_document(
        [
            [
                ("h1", BaseType.HEADING, (0.05, 0.05, 0.95, 0.13), "Top"),
                ("p1", BaseType.TEXT, (0.05, 0.16, 0.95, 0.21), "Intro"),
                ("h2", BaseType.HEADING, (0.05, 0.28, 0.70, 0.32), "Child"),
                ("p2", BaseType.TEXT, (0.05, 0.35, 0.95, 0.40), "Body"),
            ]
        ]
    )
    outline = engine.recover(outline_doc)
    cases.append(
        {
            "name": "heading-hierarchy",
            "passed": [item.level for item in outline.outline] == [1, 2]
            and outline.outline[1].parent_node_id == outline.outline[0].node_id,
            "levels": [item.level for item in outline.outline],
        }
    )

    caption_doc = build_document(
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
    caption = engine.recover(caption_doc)
    caption_relations = {
        (item.type, item.source_id, item.target_id) for item in caption.relations
    }
    cases.append(
        {
            "name": "caption-relation",
            "passed": ("caption_of", "caption", "image") in caption_relations,
            "relations": sorted(caption_relations),
        }
    )

    far_caption_doc = build_document(
        [
            [
                ("image", BaseType.IMAGE, (0.10, 0.10, 0.85, 0.35), None),
                ("body", BaseType.TEXT, (0.10, 0.75, 0.90, 0.82), "Figure 2 Far"),
            ]
        ]
    )
    far_caption = engine.recover(far_caption_doc)
    cases.append(
        {
            "name": "far-text-not-caption",
            "passed": not any(item.type == "caption_of" for item in far_caption.relations),
        }
    )

    cross_doc = build_document(
        [
            [("a", BaseType.TEXT, (0.10, 0.80, 0.90, 0.96), "Continues,")],
            [("b", BaseType.TEXT, (0.10, 0.04, 0.90, 0.18), "on next page")],
        ]
    )
    cross = engine.recover(cross_doc)
    cases.append(
        {
            "name": "cross-page-continuation",
            "passed": any(item.type == "continues_on" for item in cross.relations),
        }
    )

    negative_cross_doc = build_document(
        [
            [("a", BaseType.TEXT, (0.10, 0.80, 0.90, 0.96), "Complete.")],
            [("b", BaseType.TEXT, (0.10, 0.04, 0.90, 0.18), "New paragraph")],
        ]
    )
    negative_cross = engine.recover(negative_cross_doc)
    cases.append(
        {
            "name": "terminal-text-not-cross-page",
            "passed": not any(
                item.type == "continues_on" for item in negative_cross.relations
            ),
        }
    )

    margin_pages = []
    for index in range(3):
        margin_pages.append(
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
                    f"number_{index}",
                    BaseType.TEXT,
                    (0.45, 0.93, 0.55, 0.97),
                    str(index + 1),
                ),
            ]
        )
    margin = engine.recover(build_document(margin_pages))
    cases.append(
        {
            "name": "repeated-margin-filtering",
            "passed": margin.content_reading_order == ["body_0", "body_1", "body_2"],
            "excluded": margin.excluded_margin_element_ids,
        }
    )

    deterministic_first = engine.recover(two_column)
    deterministic_second = engine.recover(two_column)
    cases.append(
        {
            "name": "semantic-determinism",
            "passed": deterministic_first.structure_id == deterministic_second.structure_id
            and deterministic_first.semantic_digest()
            == deterministic_second.semantic_digest(),
        }
    )

    relation_results = [caption, far_caption, cross, negative_cross]
    inferred = sum(len(item.relations) for item in relation_results)
    expected = 2
    false_positive = sum(
        len(item.relations) for item in [far_caption, negative_cross]
    )
    true_positive = inferred - false_positive
    precision = true_positive / inferred if inferred else 1.0
    recall = true_positive / expected if expected else 1.0
    payload = {
        "phase": 3,
        "engine_version": engine.engine_version,
        "engine_digest": engine.engine_digest,
        "passed": all(bool(item["passed"]) for item in cases),
        "summary": {
            "cases": len(cases),
            "passed_cases": sum(bool(item["passed"]) for item in cases),
            "reading_order_exact_accuracy": 1.0
            if cases[0]["passed"]
            else 0.0,
            "relation_precision": precision,
            "relation_recall": recall,
            "false_positive_relations": false_positive,
            "evidence_coverage": min(
                item.metrics.relation_evidence_coverage for item in relation_results
            ),
        },
        "cases": cases,
        "scope": (
            "Deterministic synthetic generic-document regression only; "
            "not a production accuracy claim."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
