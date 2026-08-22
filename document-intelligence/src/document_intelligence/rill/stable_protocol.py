"""The frozen RillML Stable IPC v2 wire contract.

Preview v3 remains in :mod:`document_intelligence.rill.protocol`; this module
contains only the official 1.2.0 stable request/response shapes.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

RILL_RUNTIME_API_VERSION: Literal[2] = 2
MAX_MESSAGE_BYTES = 1024 * 1024


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class StableProtocolModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        alias_generator=_to_camel,
    )


class HandshakeRequestV2(StableProtocolModel):
    method: Literal["handshake"] = "handshake"
    request_id: str = Field(min_length=1, max_length=128)
    api_version: Literal[2] = RILL_RUNTIME_API_VERSION
    client_name: str = Field(min_length=1, max_length=96)
    client_version: str = Field(min_length=1, max_length=48)


class HealthRequestV2(StableProtocolModel):
    method: Literal["health"] = "health"
    request_id: str = Field(min_length=1, max_length=128)
    api_version: Literal[2] = RILL_RUNTIME_API_VERSION


class InvokeRequestV2(StableProtocolModel):
    method: Literal["invoke"] = "invoke"
    request_id: str = Field(min_length=1, max_length=128)
    api_version: Literal[2] = RILL_RUNTIME_API_VERSION
    capability: str = Field(min_length=1, max_length=96)
    input: Any


RuntimeRequestV2 = Annotated[
    HandshakeRequestV2 | HealthRequestV2 | InvokeRequestV2,
    Field(discriminator="method"),
]


class HandshakeResponseV2(StableProtocolModel):
    kind: Literal["handshake"] = "handshake"
    request_id: str = Field(min_length=1, max_length=128)
    api_version: Literal[2] = RILL_RUNTIME_API_VERSION
    runtime_version: str = Field(min_length=1, max_length=48)
    model_pack_id: str = Field(min_length=1, max_length=96)
    model_pack_version: str = Field(min_length=1, max_length=48)
    capabilities: list[str] = Field(min_length=1, max_length=32)
    handler_id: str = Field(min_length=1, max_length=96)
    handler_version: str = Field(min_length=1, max_length=48)
    handler_api_version: Literal[1] = 1
    effective_capabilities: list[str] = Field(min_length=1, max_length=32)


class HealthResponseV2(StableProtocolModel):
    kind: Literal["health"] = "health"
    request_id: str = Field(min_length=1, max_length=128)
    api_version: Literal[2] = RILL_RUNTIME_API_VERSION
    healthy: bool
    model_pack_id: str = Field(min_length=1, max_length=96)
    model_pack_version: str = Field(min_length=1, max_length=48)


class ResultResponseV2(StableProtocolModel):
    kind: Literal["result"] = "result"
    request_id: str = Field(min_length=1, max_length=128)
    api_version: Literal[2] = RILL_RUNTIME_API_VERSION
    output: Any


class ErrorResponseV2(StableProtocolModel):
    kind: Literal["error"] = "error"
    request_id: str = Field(min_length=1, max_length=128)
    api_version: Literal[2] = RILL_RUNTIME_API_VERSION
    code: Literal[
        "invalidJson",
        "invalidRequestId",
        "incompatibleApiVersion",
        "invalidClientIdentity",
        "unsupportedCapability",
        "noInvokeHandler",
        "handlerTimeout",
        "handlerTrap",
        "handlerOutputTooLarge",
        "handlerInvalidOutput",
        "handlerInternalError",
    ]
    message: str = Field(min_length=1, max_length=512)
    retryable: bool


RuntimeResponseV2 = Annotated[
    HandshakeResponseV2 | HealthResponseV2 | ResultResponseV2 | ErrorResponseV2,
    Field(discriminator="kind"),
]

_REQUEST_ADAPTER: TypeAdapter[RuntimeRequestV2] = TypeAdapter(RuntimeRequestV2)
_RESPONSE_ADAPTER: TypeAdapter[RuntimeResponseV2] = TypeAdapter(RuntimeResponseV2)


def encode_request(request: RuntimeRequestV2, *, max_bytes: int = MAX_MESSAGE_BYTES) -> bytes:
    payload = json.dumps(
        _REQUEST_ADAPTER.dump_python(request, mode="json", by_alias=True, exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if not payload or len(payload) > max_bytes or len(payload) > MAX_MESSAGE_BYTES:
        raise ValueError("Rill v2 request exceeds the bounded IPC message size")
    return payload


def parse_response(raw: bytes, *, max_bytes: int = MAX_MESSAGE_BYTES) -> RuntimeResponseV2:
    if not raw or len(raw) > max_bytes or len(raw) > MAX_MESSAGE_BYTES:
        raise ValueError("Rill v2 response exceeds the bounded IPC message size")
    response = _RESPONSE_ADAPTER.validate_json(raw)
    encoded = json.dumps(
        _RESPONSE_ADAPTER.dump_python(response, mode="json", by_alias=True, exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > max_bytes or len(encoded) > MAX_MESSAGE_BYTES:
        raise ValueError("validated Rill v2 response exceeds the bounded IPC message size")
    return response
