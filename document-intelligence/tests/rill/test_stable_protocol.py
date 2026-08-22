from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from document_intelligence.rill.stable_protocol import (
    HandshakeRequestV2,
    encode_request,
    parse_response,
)


def test_v2_request_and_response_match_official_flat_wire_contract() -> None:
    request = HandshakeRequestV2(
        request_id="request-1",
        client_name="lessonforge",
        client_version="1.0.3rc1",
    )
    payload = json.loads(encode_request(request))
    assert payload == {
        "apiVersion": 2,
        "clientName": "lessonforge",
        "clientVersion": "1.0.3rc1",
        "method": "handshake",
        "requestId": "request-1",
    }
    response = parse_response(
        json.dumps(
            {
                "kind": "handshake",
                "requestId": "request-1",
                "apiVersion": 2,
                "runtimeVersion": "1.2.0",
                "modelPackId": "model",
                "modelPackVersion": "1.2.0",
                "capabilities": ["cap"],
                "handlerId": "handler",
                "handlerVersion": "1.2.0",
                "handlerApiVersion": 1,
                "effectiveCapabilities": ["cap"],
            }
        ).encode()
    )
    assert response.request_id == "request-1"
    assert response.api_version == 2


def test_v2_rejects_unknown_fields_wrong_api_and_oversized_json() -> None:
    with pytest.raises(ValidationError):
        HandshakeRequestV2(
            request_id="request-1",
            client_name="lessonforge",
            client_version="1.0.3rc1",
            extra=True,
        )
    with pytest.raises(ValidationError):
        parse_response(
            b'{"kind":"health","requestId":"x","apiVersion":3,"healthy":true,"modelPackId":"m","modelPackVersion":"1"}'
        )
    with pytest.raises(ValueError):
        parse_response(b"{}", max_bytes=1)


def test_v2_error_codes_are_frozen_and_strict() -> None:
    response = parse_response(
        b'{"kind":"error","requestId":"x","apiVersion":2,"code":"handlerTimeout","message":"timeout","retryable":true}'
    )
    assert response.code == "handlerTimeout"
    with pytest.raises(ValidationError):
        parse_response(
            b'{"kind":"error","requestId":"x","apiVersion":2,"code":"madeUp","message":"bad","retryable":false}'
        )
