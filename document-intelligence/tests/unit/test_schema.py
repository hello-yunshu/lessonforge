from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

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


def test_bbox_rejects_reversed_coordinates() -> None:
    with pytest.raises(ValidationError):
        BoundingBox(x1=0.8, y1=0.2, x2=0.1, y2=0.3)


def test_document_requires_valid_evidence_graph() -> None:
    source = SourceDescriptor(
        filename="a.pdf", sha256="a" * 64, mime_type="application/pdf", size_bytes=1
    )
    page = Page(page_id="p1", index=0, width=10, height=10, element_ids=["e1"])
    element = Element(
        element_id="e1",
        page_id="p1",
        base_type=BaseType.TEXT,
        subtype="paragraph",
        bbox=BoundingBox(x1=0, y1=0, x2=1, y2=1),
        content=ElementContent(text="x"),
        confidence=Confidence(overall=1),
        evidence_ids=["missing"],
    )
    with pytest.raises(ValidationError, match="unknown evidence"):
        ParsedDocument(
            document_id="d1",
            source=source,
            pages=[page],
            elements=[element],
            evidence=[],
            parse_run_id="r1",
        )


def test_semantic_digest_ignores_evidence_timestamp_and_raw_ref() -> None:
    source = SourceDescriptor(
        filename="a.pdf", sha256="a" * 64, mime_type="application/pdf", size_bytes=1
    )
    page = Page(page_id="p1", index=0, width=10, height=10, element_ids=["e1"])
    evidence = Evidence(
        evidence_id="ev1",
        kind=EvidenceKind.NATIVE_EXTRACTION,
        producer="test",
        producer_version="1",
        model_digest="b" * 64,
        parse_run_id="r1",
        source_page_id="p1",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    element = Element(
        element_id="e1",
        page_id="p1",
        base_type=BaseType.TEXT,
        subtype="paragraph",
        bbox=BoundingBox(x1=0, y1=0, x2=1, y2=1),
        content=ElementContent(text="x"),
        confidence=Confidence(overall=1),
        evidence_ids=["ev1"],
    )
    document = ParsedDocument(
        document_id="d1",
        source=source,
        pages=[page],
        elements=[element],
        evidence=[evidence],
        parse_run_id="r1",
    )
    digest = document.semantic_digest()
    document.evidence[0].created_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
    document.evidence[0].raw_output_ref = "raw/r1.json"
    assert document.semantic_digest() == digest


def test_document_rejects_cross_page_membership() -> None:
    source = SourceDescriptor(
        filename="a.pdf", sha256="a" * 64, mime_type="application/pdf", size_bytes=1
    )
    evidence = Evidence(
        evidence_id="ev1",
        kind=EvidenceKind.NATIVE_EXTRACTION,
        producer="test",
        producer_version="1",
        model_digest="b" * 64,
        parse_run_id="r1",
        source_page_id="p1",
    )
    element = Element(
        element_id="e1",
        page_id="p1",
        base_type=BaseType.TEXT,
        subtype="paragraph",
        bbox=BoundingBox(x1=0, y1=0, x2=1, y2=1),
        content=ElementContent(text="x"),
        confidence=Confidence(overall=1),
        evidence_ids=["ev1"],
    )
    with pytest.raises(ValidationError, match="membership mismatch"):
        ParsedDocument(
            document_id="d1",
            source=source,
            pages=[Page(page_id="p1", index=0, width=10, height=10, element_ids=[])] ,
            elements=[element],
            evidence=[evidence],
            parse_run_id="r1",
        )


def test_page_indexes_must_be_contiguous() -> None:
    source = SourceDescriptor(
        filename="a.pdf", sha256="a" * 64, mime_type="application/pdf", size_bytes=1
    )
    with pytest.raises(ValidationError, match="contiguous"):
        ParsedDocument(
            document_id="d1",
            source=source,
            pages=[
                Page(page_id="p1", index=0, width=10, height=10),
                Page(page_id="p2", index=2, width=10, height=10),
            ],
            elements=[],
            evidence=[],
            parse_run_id="r1",
        )
