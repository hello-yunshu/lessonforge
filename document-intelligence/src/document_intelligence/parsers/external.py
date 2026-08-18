from __future__ import annotations

import httpx

from document_intelligence.config import ParserConfig
from document_intelligence.parsers.http_gateway import HttpNormalizedGatewayParser


class PaddleParser(HttpNormalizedGatewayParser):
    def __init__(self, config: ParserConfig, *, client: httpx.Client | None = None) -> None:
        super().__init__("paddle", config, client=client)


class OpenDocParser(HttpNormalizedGatewayParser):
    def __init__(self, config: ParserConfig, *, client: httpx.Client | None = None) -> None:
        super().__init__("opendoc", config, client=client)


class MinerUBenchmarkParser(HttpNormalizedGatewayParser):
    def __init__(self, config: ParserConfig, *, client: httpx.Client | None = None) -> None:
        super().__init__("mineru-benchmark", config, client=client)
