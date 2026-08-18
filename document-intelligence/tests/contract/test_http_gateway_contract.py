from __future__ import annotations

from copy import deepcopy

import httpx
import pytest

from document_intelligence.config import ParserConfig
from document_intelligence.exceptions import (
    ParserOutputError,
    ParserUnavailableError,
)
from document_intelligence.parsers import NativePdfParser, PaddleParser
from document_intelligence.schema import ParseRequest

DIGEST = "a" * 64


def _native_result(fixtures_dir):
    path = fixtures_dir / "native_text.pdf"
    request = ParseRequest(
        filename=path.name,
        mime_type="application/pdf",
        content=path.read_bytes(),
        parser_id="native-pdf",
    )
    return request, NativePdfParser().parse(request)


def _gateway_payload(result):
    copied = deepcopy(result)
    copied.run.parser_id = "paddle"
    copied.run.parser_version = "3.7.0"
    copied.run.parser_digest = DIGEST
    copied.run.config_digest = "b" * 64
    for item in copied.document.evidence:
        item.producer = "paddle"
        item.producer_version = "3.7.0"
        item.model_digest = DIGEST
    copied.run.semantic_output_digest = copied.document.semantic_digest()
    return {
        "gateway": {
            "parser_id": "paddle",
            "version": "3.7.0",
            "artifact_sha256": DIGEST,
        },
        "result": copied.model_dump(mode="json"),
    }


def _config(enabled=True, digest=DIGEST):
    return ParserConfig(
        enabled=enabled,
        kind="http-normalized-gateway",
        endpoint_env="TEST_PADDLE_ENDPOINT",
        expected_version="3.7.0",
        required_artifact_sha256=digest,
    )


def test_disabled_gateway_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("TEST_PADDLE_ENDPOINT", "http://parser.test")
    parser = PaddleParser(
        _config(enabled=False),
        client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500))),
    )
    health = parser.health()
    assert health.available is False
    assert "disabled" in (health.reason or "")


def test_missing_digest_fails_closed(monkeypatch, fixtures_dir) -> None:
    monkeypatch.setenv("TEST_PADDLE_ENDPOINT", "http://parser.test")
    parser = PaddleParser(
        _config(digest=None),
        client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))),
    )
    request, _ = _native_result(fixtures_dir)
    with pytest.raises(ParserUnavailableError, match="required_artifact_sha256"):
        parser.parse(request)


def test_normalized_gateway_contract(monkeypatch, fixtures_dir) -> None:
    monkeypatch.setenv("TEST_PADDLE_ENDPOINT", "http://parser.test")
    request, native = _native_result(fixtures_dir)
    payload = _gateway_payload(native)

    def handler(http_request: httpx.Request) -> httpx.Response:
        if http_request.url.path == "/healthz":
            return httpx.Response(200, json=payload["gateway"])
        if http_request.url.path == "/v1/parse":
            return httpx.Response(200, json=payload)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    parser = PaddleParser(_config(), client=client)
    assert parser.health().available is True
    result = parser.parse(request)
    assert result.run.parser_id == "paddle"
    assert result.run.parser_digest == DIGEST
    assert result.document.source.sha256 == request.sha256


def test_health_rejects_remote_digest_mismatch(monkeypatch) -> None:
    monkeypatch.setenv("TEST_PADDLE_ENDPOINT", "http://parser.test")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "parser_id": "paddle",
                "version": "3.7.0",
                "artifact_sha256": "c" * 64,
            },
        )

    parser = PaddleParser(_config(), client=httpx.Client(transport=httpx.MockTransport(handler)))
    health = parser.health()
    assert health.available is False
    assert "digest" in (health.reason or "").lower()


def test_gateway_rejects_non_object_json(monkeypatch, fixtures_dir) -> None:
    monkeypatch.setenv("TEST_PADDLE_ENDPOINT", "http://parser.test")
    request, _ = _native_result(fixtures_dir)

    def handler(http_request: httpx.Request) -> httpx.Response:
        if http_request.url.path == "/v1/parse":
            return httpx.Response(200, json=["not", "an", "object"])
        return httpx.Response(200, json={})

    parser = PaddleParser(
        _config(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(ParserOutputError, match="JSON object"):
        parser.parse(request)


def test_gateway_rejects_invalid_content_length(monkeypatch, fixtures_dir) -> None:
    monkeypatch.setenv("TEST_PADDLE_ENDPOINT", "http://parser.test")
    request, _ = _native_result(fixtures_dir)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Length": "invalid"},
            content=b"{}",
        )

    parser = PaddleParser(
        _config(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(ParserOutputError, match="Content-Length is invalid"):
        parser.parse(request)


def test_gateway_rejects_declared_oversized_response(monkeypatch, fixtures_dir) -> None:
    monkeypatch.setenv("TEST_PADDLE_ENDPOINT", "http://parser.test")
    request, _ = _native_result(fixtures_dir)
    config = _config().model_copy(update={"max_response_bytes": 16})

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Length": "1024"},
            content=b"{}",
        )

    parser = PaddleParser(
        config, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(ParserOutputError, match="exceeds configured size limit"):
        parser.parse(request)
