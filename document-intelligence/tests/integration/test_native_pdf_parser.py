from __future__ import annotations

from document_intelligence.parsers import NativePdfParser
from document_intelligence.schema import BaseType, ParseRequest


def request_for(path, parser_id="native-pdf") -> ParseRequest:
    return ParseRequest(
        filename=path.name,
        mime_type="application/pdf",
        content=path.read_bytes(),
        parser_id=parser_id,
    )


def test_native_pdf_extracts_text_and_is_reproducible(fixtures_dir) -> None:
    parser = NativePdfParser()
    first = parser.parse(request_for(fixtures_dir / "native_text.pdf"))
    second = parser.parse(request_for(fixtures_dir / "native_text.pdf"))
    texts = [e for e in first.document.elements if e.base_type in {BaseType.TEXT, BaseType.HEADING}]
    assert len(first.document.pages) == 1
    assert len(texts) >= 3
    assert "Structured Document Baseline" in "\n".join(e.content.text or "" for e in texts)
    assert first.document.semantic_digest() == second.document.semantic_digest()
    assert first.run.parse_run_id == second.run.parse_run_id
    assert first.run.semantic_output_digest == second.run.semantic_output_digest


def test_native_pdf_warns_for_image_only_scan(fixtures_dir) -> None:
    result = NativePdfParser().parse(request_for(fixtures_dir / "scanned_image.pdf"))
    assert any(item.code == "EMPTY_NATIVE_TEXT" for item in result.run.warnings)
    assert any(item.base_type == BaseType.IMAGE for item in result.document.elements)


def test_native_pdf_preserves_embedded_image_and_page_order(fixtures_dir) -> None:
    result = NativePdfParser().parse(request_for(fixtures_dir / "mixed_layout.pdf"))
    assert [page.index for page in result.document.pages] == [0, 1]
    assert any(item.base_type == BaseType.IMAGE for item in result.document.elements)
    assert all(item.evidence_ids for item in result.document.elements)


def test_run_identity_includes_context_and_implementation(fixtures_dir) -> None:
    path = fixtures_dir / "native_text.pdf"
    content = path.read_bytes()
    parser = NativePdfParser()
    first = parser.parse(
        ParseRequest(
            filename="first.pdf",
            mime_type="application/pdf",
            content=content,
            domain_pack="alpha",
        )
    )
    second = parser.parse(
        ParseRequest(
            filename="second.pdf",
            mime_type="application/pdf",
            content=content,
            domain_pack="beta",
        )
    )
    assert first.run.parse_run_id != second.run.parse_run_id
    assert first.run.request_context_digest != second.run.request_context_digest


def test_native_parser_retains_embedded_binary_artifacts(fixtures_dir) -> None:
    result = NativePdfParser().parse(request_for(fixtures_dir / "mixed_layout.pdf"))
    assert result.binary_artifacts
    for digest, content in result.binary_artifacts.items():
        import hashlib

        assert hashlib.sha256(content).hexdigest() == digest
