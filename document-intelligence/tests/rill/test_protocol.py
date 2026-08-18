from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from document_intelligence.rill.protocol import (
    DecideRequestV3,
    EnvelopeV3,
    IdentityV3,
    RuntimeResponseV3,
)


def test_v3_envelope_uses_exact_camel_case_and_rejects_unknown_fields() -> None:
    envelope = EnvelopeV3(
        request_id="request-1",
        client_identity=IdentityV3(name="host", version="0.5.0"),
        capability="org.example.decide",
        feature_schema_hash="a" * 64,
        model_generation=1,
        state_generation=2,
        payload_limit=1024 * 1024,
        request=DecideRequestV3(context={"features": {}}, deterministic_seed=42),
    )
    payload = json.loads(envelope.to_wire_bytes())
    assert payload["requestId"] == "request-1"
    assert payload["request"]["deterministicSeed"] == 42
    payload["unknown"] = True
    with pytest.raises(ValidationError):
        EnvelopeV3.model_validate(payload)


def test_v3_response_rejects_noncanonical_retryability() -> None:
    payload = {
        "requestId": "request-1",
        "apiVersion": 3,
        "runtimeIdentity": {"name": "runtime", "version": "1"},
        "modelGeneration": 1,
        "stateGeneration": 1,
        "response": {
            "kind": "error",
            "error": {"code": "handlerTimeout", "message": "timeout", "retryable": False},
        },
    }
    with pytest.raises(ValidationError):
        RuntimeResponseV3.model_validate(payload)


def test_v3_handshake_rejects_duplicate_capabilities_and_wrong_handler_api() -> None:
    base = {
        "requestId": "request-1",
        "apiVersion": 3,
        "runtimeIdentity": {"name": "runtime", "version": "1"},
        "modelGeneration": 1,
        "stateGeneration": 1,
        "response": {
            "kind": "handshake",
            "capabilities": ["org.example.shadow", "org.example.shadow"],
            "featureSchemaHash": "a" * 64,
            "handlerApiVersion": 1,
        },
    }
    with pytest.raises(ValidationError):
        RuntimeResponseV3.model_validate(base)
    base["response"]["capabilities"] = ["org.example.shadow"]
    base["response"]["handlerApiVersion"] = 2
    with pytest.raises(ValidationError):
        RuntimeResponseV3.model_validate(base)
