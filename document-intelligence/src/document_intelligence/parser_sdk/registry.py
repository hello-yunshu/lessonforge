from __future__ import annotations

from collections.abc import Iterable

from document_intelligence.exceptions import ParserUnavailableError
from document_intelligence.parser_sdk.protocol import DocumentParser
from document_intelligence.schema import ParserHealth, ParseRequest


class ParserRegistry:
    def __init__(self, parsers: Iterable[DocumentParser] = ()) -> None:
        self._parsers: dict[str, DocumentParser] = {}
        for parser in parsers:
            self.register(parser)

    def register(self, parser: DocumentParser) -> None:
        if parser.parser_id in self._parsers:
            raise ValueError(f"duplicate parser_id: {parser.parser_id}")
        self._parsers[parser.parser_id] = parser

    def get(self, parser_id: str) -> DocumentParser:
        try:
            return self._parsers[parser_id]
        except KeyError as exc:
            raise ParserUnavailableError(f"unknown parser: {parser_id}") from exc

    def health(self) -> list[ParserHealth]:
        return [self._parsers[key].health() for key in sorted(self._parsers)]

    def candidates(self, request: ParseRequest) -> list[DocumentParser]:
        return [parser for parser in self._parsers.values() if parser.supports(request)]

    def ids(self) -> list[str]:
        return sorted(self._parsers)

    def close(self) -> None:
        for parser in self._parsers.values():
            close = getattr(parser, "close", None)
            if callable(close):
                close()
