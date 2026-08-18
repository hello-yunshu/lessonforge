from __future__ import annotations

import json

from document_intelligence.parsers import NativePdfParser
from document_intelligence.schema import BaseType, ParseRequest


def test_phase1_fixture_expectations(fixtures_dir) -> None:
    manifest = json.loads((fixtures_dir / "manifest.json").read_text(encoding="utf-8"))
    parser = NativePdfParser()
    for item in manifest["fixtures"]:
        path = fixtures_dir / item["file"]
        result = parser.parse(
            ParseRequest(
                filename=path.name,
                mime_type="application/pdf",
                content=path.read_bytes(),
                parser_id="native-pdf",
            )
        )
        assert len(result.document.pages) == item["expected_pages"]
        if "expected_min_text_elements" in item:
            count = sum(
                element.base_type in {BaseType.TEXT, BaseType.HEADING}
                for element in result.document.elements
            )
            assert count >= item["expected_min_text_elements"]
        if "expected_min_images" in item:
            count = sum(element.base_type == BaseType.IMAGE for element in result.document.elements)
            assert count >= item["expected_min_images"]
        if "expected_warning" in item:
            assert any(
                warning.code == item["expected_warning"] for warning in result.run.warnings
            )
