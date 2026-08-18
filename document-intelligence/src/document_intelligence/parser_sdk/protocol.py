from __future__ import annotations

from typing import Protocol, runtime_checkable

from document_intelligence.schema import ParserHealth, ParserResult, ParseRequest


@runtime_checkable
class DocumentParser(Protocol):
    parser_id: str

    def health(self) -> ParserHealth: ...

    def supports(self, request: ParseRequest) -> bool: ...

    def parse(self, request: ParseRequest) -> ParserResult: ...
