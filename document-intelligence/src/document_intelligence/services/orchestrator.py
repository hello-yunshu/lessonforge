from __future__ import annotations

import hashlib
import traceback
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any

from document_intelligence.exceptions import ParserUnavailableError
from document_intelligence.parser_sdk import ParserRegistry
from document_intelligence.parser_sdk.protocol import DocumentParser
from document_intelligence.parser_sdk.utils import stable_id
from document_intelligence.schema import ParserResult, ParseRequest
from document_intelligence.services.store import ArtifactStore


class ParseOrchestrator:
    def __init__(
        self,
        registry: ParserRegistry,
        store: ArtifactStore,
        *,
        max_pages: int = 2000,
        max_document_elements: int = 200000,
        max_binary_artifact_bytes: int = 200 * 1024 * 1024,
        parser_suspension_checker: Callable[[str], bool] | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self.max_pages = max_pages
        self.max_document_elements = max_document_elements
        self.max_binary_artifact_bytes = max_binary_artifact_bytes
        self.parser_suspension_checker = parser_suspension_checker

    def parse(self, request: ParseRequest) -> ParserResult:
        parsers = self._route(request)
        if not parsers:
            raise ParserUnavailableError("no configured parser supports this input")
        failures: list[dict[str, Any]] = []
        fallback_result: ParserResult | None = None
        for index, parser in enumerate(parsers):
            try:
                health = parser.health()
                if not health.available:
                    raise ParserUnavailableError(
                        f"{parser.parser_id} unavailable: {health.reason or 'unknown reason'}"
                    )
                result = parser.parse(request)
                self._validate_result(request, parser.parser_id, result)
                self.store.commit_success(request, result)
                stored = self.store.read_result(result.run.parse_run_id)
                needs_ocr = any(
                    warning.code == "EMPTY_NATIVE_TEXT" for warning in stored.run.warnings
                )
                has_later_candidate = index + 1 < len(parsers)
                if parser.parser_id == "native-pdf" and needs_ocr and has_later_candidate:
                    fallback_result = stored
                    continue
                return stored
            except Exception as exc:
                failure = self._failure_payload(request, parser.parser_id, exc)
                failures.append(failure)
                self.store.record_failure(str(failure["failure_id"]), failure)
                if request.parser_id and request.parser_id != "auto":
                    raise
        if fallback_result is not None:
            return fallback_result
        message = "; ".join(f"{item['parser_id']}: {item['code']}" for item in failures)
        raise ParserUnavailableError(f"all parser candidates failed: {message}")

    def is_parser_suspended(self, parser_id: str) -> bool:
        checker = self.parser_suspension_checker
        return bool(checker is not None and checker(parser_id))

    def _route(self, request: ParseRequest) -> list[DocumentParser]:
        if request.parser_id and request.parser_id != "auto":
            if self.is_parser_suspended(request.parser_id):
                raise ParserUnavailableError(
                    "parser is temporarily suspended by the Assist circuit breaker: "
                    f"{request.parser_id}"
                )
            return [self.registry.get(request.parser_id)]
        candidates = [
            parser
            for parser in self.registry.candidates(request)
            if not self.is_parser_suspended(parser.parser_id)
        ]
        return sorted(candidates, key=lambda item: int(getattr(item, "priority", 100)))

    def _validate_result(self, request: ParseRequest, parser_id: str, result: ParserResult) -> None:
        source = result.document.source
        if source.sha256 != request.sha256:
            raise ValueError("parser output source hash mismatch")
        if source.size_bytes != len(request.content):
            raise ValueError("parser output source size mismatch")
        if source.mime_type != request.mime_type:
            raise ValueError("parser output source MIME mismatch")
        if source.filename != request.filename:
            raise ValueError("parser output source filename mismatch")
        if result.document.parse_run_id != result.run.parse_run_id:
            raise ValueError("document and run IDs differ")
        if result.run.input_sha256 != request.sha256:
            raise ValueError("run input hash mismatch")
        if result.run.request_context_digest != request.context_digest():
            raise ValueError("run request context digest mismatch")
        if result.run.parser_id != parser_id:
            raise ValueError("parser result reports a different parser_id")
        if len(result.document.pages) > self.max_pages:
            raise ValueError(
                "parser output page count exceeds limit: "
                f"{len(result.document.pages)} > {self.max_pages}"
            )
        if len(result.document.elements) > self.max_document_elements:
            raise ValueError(
                "parser output element count exceeds limit: "
                f"{len(result.document.elements)} > {self.max_document_elements}"
            )
        artifact_bytes = sum(len(content) for content in result.binary_artifacts.values())
        if artifact_bytes > self.max_binary_artifact_bytes:
            raise ValueError(
                "parser binary artifacts exceed limit: "
                f"{artifact_bytes} > {self.max_binary_artifact_bytes} bytes"
            )
        for expected_digest, content in result.binary_artifacts.items():
            if hashlib.sha256(content).hexdigest() != expected_digest:
                raise ValueError("parser binary artifact digest mismatch")
        digest = result.document.semantic_digest()
        if result.run.semantic_output_digest != digest:
            raise ValueError("semantic output digest mismatch")

    @staticmethod
    def _failure_payload(
        request: ParseRequest, parser_id: str, exc: Exception
    ) -> dict[str, Any]:
        code = getattr(exc, "code", "UNEXPECTED_ERROR")
        severity = getattr(exc, "severity", "P1")
        occurred_at = datetime.now(timezone.utc).isoformat()
        failure_id = stable_id(
            "failure",
            request.sha256,
            request.context_digest(),
            parser_id,
            code,
            hashlib.sha256(str(exc).encode("utf-8")).hexdigest(),
            occurred_at,
        )
        return {
            "failure_id": failure_id,
            "input_sha256": request.sha256,
            "request_context_digest": request.context_digest(),
            "filename": request.filename,
            "parser_id": parser_id,
            "code": code,
            "severity": severity,
            "message": str(exc),
            "exception_type": type(exc).__name__,
            "retryable": bool(getattr(exc, "retryable", False)),
            "occurred_at": occurred_at,
            "traceback": "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )[-8000:],
        }
