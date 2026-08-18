from __future__ import annotations

import json
import math
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.rill.models import (
    RILL_MAX_MESSAGE_BYTES,
    SUPPORTED_RILL_HANDLER_API_VERSION,
)
from document_intelligence.schema import SHA256_PATTERN

RILL_RUNTIME_API_VERSION_V3 = 3


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ProtocolModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        alias_generator=_to_camel,
    )


class IdentityV3(ProtocolModel):
    name: str = Field(min_length=1, max_length=96)
    version: str = Field(min_length=1, max_length=48)


class HandshakeRequestV3(ProtocolModel):
    method: Literal["handshake"] = "handshake"


class HealthRequestV3(ProtocolModel):
    method: Literal["health"] = "health"


class ObserveRequestV3(ProtocolModel):
    method: Literal["observe"] = "observe"
    event: dict[str, Any]


class DecideRequestV3(ProtocolModel):
    method: Literal["decide"] = "decide"
    context: dict[str, Any]
    deterministic_seed: int | None = Field(default=None, ge=0)


class FeedbackRequestV3(ProtocolModel):
    method: Literal["feedback"] = "feedback"
    decision_id: str = Field(min_length=1, max_length=128)
    selected_arm: int = Field(ge=0)
    reward: float
    outcome_time_ms: int = Field(ge=0)
    generation: int = Field(ge=0)

    @field_validator("reward")
    @classmethod
    def reward_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("reward must be finite")
        return value


class InspectRequestV3(ProtocolModel):
    method: Literal["inspect"] = "inspect"


class SnapshotRequestV3(ProtocolModel):
    method: Literal["snapshot"] = "snapshot"


class ResetRequestV3(ProtocolModel):
    method: Literal["reset"] = "reset"
    expected_state_generation: int = Field(ge=0)


RuntimeRequestV3 = Annotated[
    Union[
        HandshakeRequestV3,
        HealthRequestV3,
        ObserveRequestV3,
        DecideRequestV3,
        FeedbackRequestV3,
        InspectRequestV3,
        SnapshotRequestV3,
        ResetRequestV3,
    ],
    Field(discriminator="method"),
]


class EnvelopeV3(ProtocolModel):
    request_id: str = Field(min_length=1, max_length=128)
    api_version: Literal[3] = RILL_RUNTIME_API_VERSION_V3
    client_identity: IdentityV3
    capability: str | None = Field(default=None, max_length=96)
    deadline_unix_ms: int | None = Field(default=None, ge=0)
    feature_schema_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    model_generation: int = Field(ge=0)
    state_generation: int = Field(ge=0)
    payload_limit: int = Field(gt=0, le=RILL_MAX_MESSAGE_BYTES)
    request: RuntimeRequestV3

    @model_validator(mode="after")
    def validate_capability_and_schema(self) -> EnvelopeV3:
        control = isinstance(self.request, (HandshakeRequestV3, HealthRequestV3))
        if control:
            if self.capability is not None:
                raise ValueError("control requests cannot carry a capability")
        else:
            if not self.capability:
                raise ValueError("stateful requests require a capability")
            if self.feature_schema_hash is None:
                raise ValueError("stateful requests require a feature schema hash")
        encoded = self.to_wire_bytes()
        if len(encoded) > self.payload_limit or len(encoded) > RILL_MAX_MESSAGE_BYTES:
            raise ValueError("Rill request exceeds its payload limit")
        return self

    def to_wire_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json", by_alias=True, exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


class HandshakeBodyV3(ProtocolModel):
    kind: Literal["handshake"] = "handshake"
    capabilities: list[str] = Field(min_length=1, max_length=32)
    feature_schema_hash: str = Field(pattern=SHA256_PATTERN)
    handler_api_version: Literal[1] = SUPPORTED_RILL_HANDLER_API_VERSION

    @field_validator("capabilities")
    @classmethod
    def capabilities_are_bounded_and_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("runtime capabilities contain duplicates")
        if any(not value or len(value) > 96 for value in values):
            raise ValueError("invalid runtime capability")
        return values


class HealthBodyV3(ProtocolModel):
    kind: Literal["health"] = "health"
    healthy: bool


class ResultBodyV3(ProtocolModel):
    kind: Literal["result"] = "result"
    output: Any


class InspectionBodyV3(ProtocolModel):
    kind: Literal["inspection"] = "inspection"
    summary: Any


class SnapshotBodyV3(ProtocolModel):
    kind: Literal["snapshot"] = "snapshot"
    state_schema_version: int = Field(ge=1)
    state_checksum: str = Field(pattern=SHA256_PATTERN)
    state: str


class ResetBodyV3(ProtocolModel):
    kind: Literal["reset"] = "reset"
    reset: bool


class RuntimeErrorV3(ProtocolModel):
    code: Literal[
        "invalidJson",
        "invalidRequestId",
        "invalidClientIdentity",
        "incompatibleApiVersion",
        "invalidEnvelope",
        "payloadTooLarge",
        "unsupportedCapability",
        "stateMismatch",
        "expiredRequest",
        "incompatibleGeneration",
        "duplicateFeedback",
        "handlerTimeout",
        "handlerTrap",
        "handlerOutputTooLarge",
        "handlerInvalidOutput",
        "invalidState",
        "internal",
    ]
    message: str = Field(min_length=1, max_length=512)
    retryable: bool

    @model_validator(mode="after")
    def retryability_is_canonical(self) -> RuntimeErrorV3:
        expected = self.code in {"stateMismatch", "handlerTimeout", "internal"}
        if self.retryable != expected:
            raise ValueError("runtime retryability differs from the IPC v3 contract")
        return self


class ErrorBodyV3(ProtocolModel):
    kind: Literal["error"] = "error"
    error: RuntimeErrorV3


RuntimeResponseBodyV3 = Annotated[
    Union[
        HandshakeBodyV3,
        HealthBodyV3,
        ResultBodyV3,
        InspectionBodyV3,
        SnapshotBodyV3,
        ResetBodyV3,
        ErrorBodyV3,
    ],
    Field(discriminator="kind"),
]


class RuntimeResponseV3(ProtocolModel):
    request_id: str = Field(min_length=1, max_length=128)
    api_version: Literal[3] = RILL_RUNTIME_API_VERSION_V3
    runtime_identity: IdentityV3
    model_generation: int = Field(ge=0)
    state_generation: int = Field(ge=0)
    response: RuntimeResponseBodyV3

    @classmethod
    def from_wire_bytes(cls, payload: bytes, *, max_bytes: int) -> RuntimeResponseV3:
        if not payload or len(payload) > max_bytes or len(payload) > RILL_MAX_MESSAGE_BYTES:
            raise ValueError("Rill response is empty or exceeds the configured limit")
        decoded = json.loads(payload)
        result = cls.model_validate(decoded)
        encoded = json.dumps(
            result.model_dump(mode="json", by_alias=True, exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > RILL_MAX_MESSAGE_BYTES:
            raise ValueError("validated Rill response exceeds the protocol maximum")
        return result
