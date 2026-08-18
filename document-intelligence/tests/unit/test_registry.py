from __future__ import annotations

import pytest

from document_intelligence.parser_sdk import ParserRegistry
from document_intelligence.parsers import NativePdfParser


def test_registry_rejects_duplicate_parser_id() -> None:
    registry = ParserRegistry([NativePdfParser()])
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(NativePdfParser())


def test_registry_lists_health() -> None:
    registry = ParserRegistry([NativePdfParser()])
    health = registry.health()
    assert health[0].parser_id == "native-pdf"
    assert health[0].available is True
