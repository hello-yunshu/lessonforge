from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.schema import SAFE_ID_PATTERN, SHA256_PATTERN, validate_safe_id

RILL_SHADOW_SCHEMA_VERSION = "0.5"
RILL_FEATURE_SCHEMA_VERSION = "1.0"
RILL_MAX_MESSAGE_BYTES = 1024 * 1024
SUPPORTED_RILL_HANDLER_API_VERSION = 1


class RillModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ShadowAction(StrEnum):
    ACCEPT = "ACCEPT"
    RETRY = "RETRY"
    REPROCESS_HIGH_RES = "REPROCESS_HIGH_RES"
    USE_SECONDARY_PARSER = "USE_SECONDARY_PARSER"
    USE_SPECIALIST_PARSER = "USE_SPECIALIST_PARSER"
    USE_DOMAIN_ADAPTER = "USE_DOMAIN_ADAPTER"
    VLM_REVIEW = "VLM_REVIEW"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    QUARANTINE = "QUARANTINE"


ACTION_ARMS: tuple[ShadowAction, ...] = tuple(ShadowAction)
ACTION_TO_ARM = {action: index for index, action in enumerate(ACTION_ARMS)}

RILL_FEATURE_ORDER: tuple[str, ...] = (
    "parse.page_count",
    "parse.element_count",
    "parse.average_confidence",
    "parse.minimum_confidence",
    "parse.p0_warnings",
    "parse.p1_warnings",
    "parse.p2_warnings",
    "parse.empty_native_text",
    "parse.duration_ms_log1p",
    "parse.estimated_cost_usd_log1p",
    "match.present",
    "match.top1_score",
    "match.margin",
    "match.candidate_count",
    "match.safe_standard_reuse",
    "structure.present",
    "structure.reading_order_coverage",
    "structure.relation_evidence_coverage",
    "structure.consistency_score",
    "structure.diagnostics_warning",
    "structure.diagnostics_error",
    "structure.cross_page_relations",
    "domain.present",
    "domain.fallback_used",
    "domain.error_findings",
    "domain.evidence_coverage",
)


class ShadowEvaluationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    RUNTIME_ERROR = "runtime_error"


class FeedbackSeverity(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class ParseSignals(RillModel):
    page_count: int = Field(ge=0)
    element_count: int = Field(ge=0)
    average_confidence: float = Field(ge=0.0, le=1.0)
    minimum_confidence: float = Field(ge=0.0, le=1.0)
    p0_warnings: int = Field(ge=0)
    p1_warnings: int = Field(ge=0)
    p2_warnings: int = Field(ge=0)
    empty_native_text: bool = False
    duration_ms: float = Field(ge=0.0)
    estimated_cost_usd: float = Field(ge=0.0)


class MatchSignals(RillModel):
    decision: Literal["safe_standard_reuse", "ambiguous", "no_match"]
    top1_score: float = Field(ge=0.0, le=1.0)
    margin: float = Field(ge=0.0, le=1.0)
    candidate_count: int = Field(ge=0)
    safe_standard_reuse: bool


class StructureSignals(RillModel):
    reading_order_coverage: float = Field(ge=0.0, le=1.0)
    relation_evidence_coverage: float = Field(ge=0.0, le=1.0)
    consistency_score: float = Field(ge=0.0, le=1.0)
    diagnostics_info: int = Field(ge=0)
    diagnostics_warning: int = Field(ge=0)
    diagnostics_error: int = Field(ge=0)
    cross_page_relations: int = Field(ge=0)


class DomainSignals(RillModel):
    status: Literal["succeeded", "fallback_generic"]
    annotations: int = Field(ge=0)
    relations: int = Field(ge=0)
    validation_findings: int = Field(ge=0)
    error_findings: int = Field(ge=0)
    evidence_coverage: float = Field(ge=0.0, le=1.0)
    fallback_used: bool


class ShadowSignals(RillModel):
    parse: ParseSignals
    matching: MatchSignals | None = None
    structure: StructureSignals | None = None
    domain: DomainSignals | None = None


class RillObserveEvent(RillModel):
    schema_version: Literal["0.5"] = RILL_SHADOW_SCHEMA_VERSION
    event_id: str = Field(pattern=SAFE_ID_PATTERN)
    parse_run_id: str = Field(pattern=SAFE_ID_PATTERN)
    parser_id: str = Field(min_length=1, max_length=127)
    document_family: str | None = Field(default=None, max_length=127)
    structure_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    domain_result_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    signals: ShadowSignals
    shadow_only: Literal[True] = True
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("generated_at")
    @classmethod
    def generated_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        return value

    def feature_dict(self) -> dict[str, float]:
        match = self.signals.matching
        structure = self.signals.structure
        domain = self.signals.domain
        parse = self.signals.parse
        features = {
            "parse.page_count": float(parse.page_count),
            "parse.element_count": float(parse.element_count),
            "parse.average_confidence": parse.average_confidence,
            "parse.minimum_confidence": parse.minimum_confidence,
            "parse.p0_warnings": float(parse.p0_warnings),
            "parse.p1_warnings": float(parse.p1_warnings),
            "parse.p2_warnings": float(parse.p2_warnings),
            "parse.empty_native_text": float(parse.empty_native_text),
            "parse.duration_ms_log1p": math.log1p(parse.duration_ms),
            "parse.estimated_cost_usd_log1p": math.log1p(parse.estimated_cost_usd),
            "match.present": float(match is not None),
            "match.top1_score": match.top1_score if match else 0.0,
            "match.margin": match.margin if match else 0.0,
            "match.candidate_count": float(match.candidate_count if match else 0),
            "match.safe_standard_reuse": float(match.safe_standard_reuse if match else False),
            "structure.present": float(structure is not None),
            "structure.reading_order_coverage": (
                structure.reading_order_coverage if structure else 0.0
            ),
            "structure.relation_evidence_coverage": (
                structure.relation_evidence_coverage if structure else 0.0
            ),
            "structure.consistency_score": structure.consistency_score if structure else 0.0,
            "structure.diagnostics_warning": float(
                structure.diagnostics_warning if structure else 0
            ),
            "structure.diagnostics_error": float(structure.diagnostics_error if structure else 0),
            "structure.cross_page_relations": float(
                structure.cross_page_relations if structure else 0
            ),
            "domain.present": float(domain is not None),
            "domain.fallback_used": float(domain.fallback_used if domain else False),
            "domain.error_findings": float(domain.error_findings if domain else 0),
            "domain.evidence_coverage": domain.evidence_coverage if domain else 0.0,
        }
        if tuple(features) != RILL_FEATURE_ORDER:
            raise RuntimeError("Rill feature extraction order differs from the frozen schema")
        return features


class PolicySuggestion(RillModel):
    decision_id: str = Field(pattern=SAFE_ID_PATTERN)
    action: ShadowAction
    selected_arm: int = Field(ge=0)
    policy_version: str = Field(min_length=1, max_length=127)
    confidence: float = Field(ge=0.0, le=1.0)
    reason_codes: list[str] = Field(min_length=1, max_length=32)
    source: Literal["static_policy", "rill_runtime", "reference_runtime"]
    model_generation: int = Field(default=0, ge=0)
    state_generation: int = Field(default=0, ge=0)

    @field_validator("reason_codes")
    @classmethod
    def reason_codes_are_safe(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("reason codes contain duplicates")
        for value in values:
            if not value or len(value) > 127 or not all(
                character.isalnum() or character in "_-" for character in value
            ):
                raise ValueError("invalid reason code")
        return values

    @model_validator(mode="after")
    def arm_matches_action(self) -> PolicySuggestion:
        if self.selected_arm != ACTION_TO_ARM[self.action]:
            raise ValueError("selected arm does not match action")
        return self


class RuntimeIdentity(RillModel):
    name: str = Field(min_length=1, max_length=96)
    version: str = Field(min_length=1, max_length=48)
    feature_schema_hash: str = Field(pattern=SHA256_PATTERN)
    handler_api_version: Literal[1] = SUPPORTED_RILL_HANDLER_API_VERSION
    capabilities: list[str] = Field(min_length=1, max_length=32)

    @field_validator("capabilities")
    @classmethod
    def capabilities_are_bounded_and_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("runtime capabilities contain duplicates")
        if any(not value or len(value) > 96 for value in values):
            raise ValueError("invalid runtime capability")
        return values


class ShadowEvaluation(RillModel):
    evaluation_id: str = Field(pattern=SAFE_ID_PATTERN)
    feature_schema_hash: str = Field(pattern=SHA256_PATTERN)
    observe_event: RillObserveEvent
    static_suggestion: PolicySuggestion
    rill_suggestion: PolicySuggestion | None = None
    runtime_identity: RuntimeIdentity | None = None
    backend_name: str = Field(min_length=1, max_length=127)
    input_model_generation: int = Field(ge=0)
    input_state_generation: int = Field(ge=0)
    status: ShadowEvaluationStatus
    runtime_error_code: str | None = Field(default=None, max_length=127)
    runtime_error_message: str | None = Field(default=None, max_length=1000)
    no_action_executed: Literal[True] = True
    shadow_only: Literal[True] = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def created_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def status_consistent(self) -> ShadowEvaluation:
        if self.status == ShadowEvaluationStatus.SUCCEEDED:
            if self.rill_suggestion is None or self.runtime_identity is None:
                raise ValueError("successful shadow evaluation requires a Rill suggestion")
            if self.runtime_error_code is not None or self.runtime_error_message is not None:
                raise ValueError("successful evaluation cannot contain a runtime error")
        else:
            if self.rill_suggestion is not None:
                raise ValueError("failed runtime evaluation cannot contain a Rill suggestion")
            if not self.runtime_error_code or not self.runtime_error_message:
                raise ValueError("runtime failure requires a stable error")
        return self

    def semantic_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("created_at", None)
        payload["observe_event"].pop("generated_at", None)
        return payload

    def semantic_digest(self) -> str:
        encoded = json.dumps(
            self.semantic_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class ShadowFeedbackInput(RillModel):
    evaluation_id: str = Field(pattern=SAFE_ID_PATTERN)
    actual_action: ShadowAction
    decision_correct: bool
    error_scope: str = Field(min_length=1, max_length=127)
    error_type: str = Field(min_length=1, max_length=127)
    severity: FeedbackSeverity
    human_edit_seconds: float = Field(default=0.0, ge=0.0, le=86400.0)
    eligible_for_training: bool = False
    outcome_time_ms: int = Field(ge=0)


class ShadowFeedbackRecord(RillModel):
    feedback_id: str = Field(pattern=SAFE_ID_PATTERN)
    evaluation_id: str = Field(pattern=SAFE_ID_PATTERN)
    decision_id: str = Field(pattern=SAFE_ID_PATTERN)
    selected_arm: int = Field(ge=0)
    actual_action: ShadowAction
    decision_correct: bool
    error_scope: str = Field(min_length=1, max_length=127)
    error_type: str = Field(min_length=1, max_length=127)
    severity: FeedbackSeverity
    human_edit_seconds: float = Field(ge=0.0, le=86400.0)
    eligible_for_training: bool
    reward: float = Field(ge=-100.0, le=10.0)
    runtime_feedback_accepted: bool
    runtime_error_code: str | None = Field(default=None, max_length=127)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def feedback_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def runtime_status_consistent(self) -> ShadowFeedbackRecord:
        if self.runtime_feedback_accepted and self.runtime_error_code is not None:
            raise ValueError("accepted runtime feedback cannot carry an error")
        if not self.runtime_feedback_accepted and not self.runtime_error_code:
            raise ValueError("rejected runtime feedback requires an error code")
        return self

    def semantic_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("created_at", None)
        return payload

    def semantic_digest(self) -> str:
        encoded = json.dumps(
            self.semantic_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class DriftState(RillModel):
    schema_version: Literal["1"] = "1"
    sample_count: int = Field(default=0, ge=0)
    mean_error: float = Field(default=0.0, ge=0.0, le=1.0)
    cumulative: float = 0.0
    minimum_cumulative: float = 0.0
    recent_errors: list[int] = Field(default_factory=list, max_length=200)
    alert_count: int = Field(default=0, ge=0)
    state_generation: int = Field(default=0, ge=0)

    @field_validator("recent_errors")
    @classmethod
    def binary_errors(cls, values: list[int]) -> list[int]:
        if any(value not in {0, 1} for value in values):
            raise ValueError("recent errors must be binary")
        return values


class DriftAlert(RillModel):
    alert_id: str = Field(pattern=SAFE_ID_PATTERN)
    sample_count: int = Field(ge=1)
    recent_error_rate: float = Field(ge=0.0, le=1.0)
    baseline_error_rate: float = Field(ge=0.0, le=1.0)
    page_hinkley_distance: float = Field(ge=0.0)
    threshold: float = Field(gt=0.0)
    reason_codes: list[str] = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReplayMetrics(RillModel):
    total_evaluations: int = Field(ge=0)
    feedback_records: int = Field(ge=0)
    rill_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    static_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    suggestion_disagreements: int = Field(ge=0)
    rill_accept_on_p0_p1: int = Field(ge=0)
    static_accept_on_p0_p1: int = Field(ge=0)
    mean_reward: float | None = None
    mean_human_edit_seconds: float | None = Field(default=None, ge=0.0)
    drift_alerts: int = Field(ge=0)
    safe_for_assist_consideration: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)


class ShadowSnapshotRecord(RillModel):
    snapshot_id: str = Field(pattern=SAFE_ID_PATTERN)
    feature_schema_hash: str = Field(pattern=SHA256_PATTERN)
    runtime_name: str = Field(min_length=1, max_length=96)
    runtime_version: str = Field(min_length=1, max_length=48)
    model_generation: int = Field(ge=0)
    state_generation: int = Field(ge=0)
    state_schema_version: int = Field(ge=1)
    state_checksum: str = Field(pattern=SHA256_PATTERN)
    state_ref: str = Field(min_length=1, max_length=1000)
    drift_state_checksum: str = Field(pattern=SHA256_PATTERN)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ShadowResetRecord(RillModel):
    reset_id: str = Field(pattern=SAFE_ID_PATTERN)
    pre_reset_snapshot_id: str = Field(pattern=SAFE_ID_PATTERN)
    expected_state_generation: int = Field(ge=0)
    reset_state_generation: int = Field(ge=0)
    runtime_reset: bool
    local_drift_reset: bool
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def canonical_json_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stable_rill_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]
    value = f"{prefix}-{digest}"
    return validate_safe_id(value)
