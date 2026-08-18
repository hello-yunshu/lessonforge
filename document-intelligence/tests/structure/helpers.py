from __future__ import annotations

import hashlib
from collections.abc import Sequence

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
                    producer="fixture",
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
                    subtype=f"fixture_{base_type.value}",
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
            filename="fixture.pdf",
            sha256=source_hash,
            mime_type="application/pdf",
            size_bytes=1,
        ),
        pages=pages,
        elements=elements,
        evidence=evidence,
        parse_run_id=run_id,
    )
