from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import ValidationError

from document_intelligence.config import ParserConfig
from document_intelligence.exceptions import (
    ParserDigestMismatchError,
    ParserOutputError,
    ParserTimeoutError,
    ParserUnavailableError,
    ParserVersionMismatchError,
    UnsupportedInputError,
)
from document_intelligence.schema import ParserHealth, ParserResult, ParseRequest

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class HttpNormalizedGatewayParser:
    """Adapter for an engine-specific gateway returning canonical ``ParserResult`` JSON."""

    capabilities = ["application/pdf", "image/*", "normalized-gateway"]

    def __init__(
        self,
        parser_id: str,
        config: ParserConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.parser_id = parser_id
        self.config = config
        self.priority = config.priority
        self.endpoint = config.endpoint()
        self._client = client or httpx.Client(timeout=config.parse_timeout_seconds)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def supports(self, request: ParseRequest) -> bool:
        if not self.config.enabled or not self.endpoint:
            return False
        return request.mime_type == "application/pdf" or request.mime_type.startswith("image/")

    def health(self) -> ParserHealth:
        preflight = self._preflight_reason()
        if preflight:
            return ParserHealth(
                parser_id=self.parser_id,
                available=False,
                enabled=self.config.enabled,
                version=self.config.expected_version,
                artifact_digest=self.config.required_artifact_sha256,
                reason=preflight,
                capabilities=self.capabilities,
            )
        endpoint = self.endpoint
        if endpoint is None:
            return ParserHealth(
                parser_id=self.parser_id,
                available=False,
                enabled=self.config.enabled,
                version=self.config.expected_version,
                artifact_digest=self.config.required_artifact_sha256,
                reason="parser endpoint is not configured",
                capabilities=self.capabilities,
            )
        try:
            with self._client.stream(
                "GET",
                f"{endpoint}{self.config.health_path}",
                timeout=self.config.health_timeout_seconds,
            ) as response:
                response.raise_for_status()
                body = self._read_limited_response(
                    response, limit=min(self.config.max_response_bytes, 1024 * 1024)
                )
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ParserOutputError("health response must be a JSON object")
            self._verify_remote_identity(payload)
        except Exception as exc:
            return ParserHealth(
                parser_id=self.parser_id,
                available=False,
                enabled=True,
                version=self.config.expected_version,
                artifact_digest=self.config.required_artifact_sha256,
                reason=f"health check failed: {type(exc).__name__}: {exc}",
                capabilities=self.capabilities,
            )
        return ParserHealth(
            parser_id=self.parser_id,
            available=True,
            enabled=True,
            version=str(payload["version"]),
            artifact_digest=str(payload["artifact_sha256"]),
            capabilities=self.capabilities,
        )

    def parse(self, request: ParseRequest) -> ParserResult:
        if request.mime_type != "application/pdf" and not request.mime_type.startswith("image/"):
            raise UnsupportedInputError(f"{self.parser_id} does not support {request.mime_type}")
        preflight = self._preflight_reason()
        if preflight:
            raise ParserUnavailableError(f"{self.parser_id}: {preflight}")
        endpoint = self.endpoint
        if endpoint is None:
            raise ParserUnavailableError(
                f"{self.parser_id}: parser endpoint is not configured"
            )
        try:
            with self._client.stream(
                "POST",
                f"{endpoint}{self.config.parse_path}",
                files={"file": (request.filename, request.content, request.mime_type)},
                data={
                    "input_sha256": request.sha256,
                    "request_context_digest": request.context_digest(),
                    "domain_pack": request.domain_pack or "",
                    "options_json": json.dumps(request.options, ensure_ascii=False, sort_keys=True),
                },
                timeout=self.config.parse_timeout_seconds,
            ) as response:
                response.raise_for_status()
                body = self._read_limited_response(
                    response, limit=self.config.max_response_bytes
                )
        except httpx.TimeoutException as exc:
            raise ParserTimeoutError(f"{self.parser_id} timed out") from exc
        except httpx.HTTPError as exc:
            raise ParserUnavailableError(f"{self.parser_id} request failed: {exc}") from exc
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise TypeError("gateway response must be a JSON object")
            identity = payload.get("gateway", {})
            if not isinstance(identity, dict):
                raise TypeError("gateway identity must be a JSON object")
            self._verify_remote_identity(identity)
            result_payload = payload.get("result", payload)
            result = ParserResult.model_validate(result_payload)
        except (ValueError, ValidationError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ParserOutputError(
                f"{self.parser_id} returned invalid normalized output: {exc}"
            ) from exc
        if result.document.source.sha256 != request.sha256:
            raise ParserOutputError("gateway result input hash does not match request")
        if result.run.input_sha256 != request.sha256:
            raise ParserOutputError("gateway run input hash does not match request")
        if result.run.request_context_digest != request.context_digest():
            raise ParserOutputError("gateway request context digest mismatch")
        if result.run.parser_id != self.parser_id:
            raise ParserOutputError("gateway result parser_id does not match configured parser")
        if result.run.parser_version != self.config.expected_version:
            raise ParserVersionMismatchError(
                f"result version {result.run.parser_version!r} != {self.config.expected_version!r}"
            )
        if result.run.parser_digest != self.config.required_artifact_sha256:
            raise ParserDigestMismatchError("result artifact digest mismatch")
        if result.run.semantic_output_digest != result.document.semantic_digest():
            raise ParserOutputError("gateway semantic output digest mismatch")
        return result


    @staticmethod
    def _read_limited_response(response: httpx.Response, *, limit: int) -> bytes:
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                declared_length = int(content_length)
            except ValueError as exc:
                raise ParserOutputError("response Content-Length is invalid") from exc
            if declared_length < 0 or declared_length > limit:
                raise ParserOutputError("gateway response exceeds configured size limit")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > limit:
                raise ParserOutputError("gateway response exceeds configured size limit")
            chunks.append(chunk)
        return b"".join(chunks)

    def _preflight_reason(self) -> str | None:
        if not self.config.enabled:
            return "disabled by configuration"
        if not self.endpoint:
            return f"missing endpoint environment variable: {self.config.endpoint_env}"
        digest = self.config.required_artifact_sha256
        if not digest or not _SHA256_RE.fullmatch(digest):
            return "required_artifact_sha256 must be a pinned lowercase SHA-256"
        return None

    def _verify_remote_identity(self, payload: Mapping[str, Any]) -> None:
        remote_id = str(payload.get("parser_id", ""))
        version = str(payload.get("version", ""))
        digest = str(payload.get("artifact_sha256", ""))
        if remote_id != self.parser_id:
            raise ParserUnavailableError(
                f"remote parser_id {remote_id!r} does not match {self.parser_id!r}"
            )
        if version != self.config.expected_version:
            raise ParserVersionMismatchError(
                f"remote version {version!r} != pinned {self.config.expected_version!r}"
            )
        if digest != self.config.required_artifact_sha256:
            raise ParserDigestMismatchError("remote artifact digest mismatch")
