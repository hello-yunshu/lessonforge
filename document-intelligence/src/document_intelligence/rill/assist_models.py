from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.rill.models import ShadowAction
from document_intelligence.schema import SAFE_ID_PATTERN, SHA256_PATTERN

ASSIST_SCHEMA_VERSION = "0.6"
BOUNDED_AUTO_ENABLED = False


class AssistModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    def semantic_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        for field in (
            "created_at",
            "activated_at",
            "revoked_at",
            "suspended_at",
            "resumed_at",
        ):
            payload.pop(field, None)
        return payload

    def semantic_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.semantic_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


class AssistEvidenceOrigin(StrEnum):
    PRODUCTION = "production"
    GOLD = "gold"
    CHALLENGE = "challenge"
    SYNTHETIC = "synthetic"
    LEGACY_UNCLASSIFIED = "legacy_unclassified"


class AssistReviewerRole(StrEnum):
    REVIEWER = "reviewer"
    DOMAIN_EXPERT = "domain_expert"


class Tier1AssistAction(StrEnum):
    RETRY = ShadowAction.RETRY.value
    REPROCESS_HIGH_RES = ShadowAction.REPROCESS_HIGH_RES.value
    USE_SECONDARY_PARSER = ShadowAction.USE_SECONDARY_PARSER.value
    USE_SPECIALIST_PARSER = ShadowAction.USE_SPECIALIST_PARSER.value
    HUMAN_REVIEW = ShadowAction.HUMAN_REVIEW.value
    QUARANTINE = ShadowAction.QUARANTINE.value


TIER1_ACTIONS: tuple[Tier1AssistAction, ...] = tuple(Tier1AssistAction)


class AssistExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


class AssistQueueKind(StrEnum):
    HUMAN_REVIEW = "human_review"
    QUARANTINE = "quarantine"


class AssistEvidenceAttestation(AssistModel):
    schema_version: Literal["0.6"] = ASSIST_SCHEMA_VERSION
    attestation_id: str = Field(pattern=SAFE_ID_PATTERN)
    feedback_id: str = Field(pattern=SAFE_ID_PATTERN)
    reviewer_role: AssistReviewerRole
    evidence_origin: AssistEvidenceOrigin
    reviewer_id_hash: str = Field(pattern=SHA256_PATTERN)
    dataset_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    approved_for_qualification: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def created_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def approved_evidence_is_strict(self) -> AssistEvidenceAttestation:
        if self.approved_for_qualification:
            if self.reviewer_role != AssistReviewerRole.DOMAIN_EXPERT:
                raise ValueError("qualification evidence requires a domain expert")
            if self.evidence_origin not in {
                AssistEvidenceOrigin.PRODUCTION,
                AssistEvidenceOrigin.GOLD,
                AssistEvidenceOrigin.CHALLENGE,
            }:
                raise ValueError("synthetic or unclassified evidence cannot qualify Assist")
            if self.dataset_id is None:
                raise ValueError("qualification evidence requires a dataset_id")
        return self


class AssistQualificationReport(AssistModel):
    schema_version: Literal["0.6"] = ASSIST_SCHEMA_VERSION
    report_id: str = Field(pattern=SAFE_ID_PATTERN)
    feature_schema_hash: str = Field(pattern=SHA256_PATTERN)
    runtime_name: str = Field(min_length=1, max_length=96)
    runtime_version: str = Field(min_length=1, max_length=48)
    runtime_artifact_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    model_artifact_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    handler_artifact_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    model_generation: int = Field(ge=0)
    state_generation: int = Field(ge=0)
    replay_digest: str = Field(pattern=SHA256_PATTERN)
    total_feedback_count: int = Field(ge=0)
    eligible_feedback_count: int = Field(ge=0)
    expert_feedback_count: int = Field(ge=0)
    production_like_feedback_count: int = Field(ge=0)
    rill_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    static_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    rill_accept_on_p0_p1: int = Field(ge=0)
    active_drift_alerts: int = Field(ge=0)
    action_feedback_counts: dict[Tier1AssistAction, int] = Field(default_factory=dict)
    requested_actions: list[Tier1AssistAction] = Field(min_length=1)
    qualified_actions: list[Tier1AssistAction] = Field(default_factory=list)
    qualified: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)
    attestation_ids: list[str] = Field(default_factory=list)
    test_only: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime

    @field_validator("requested_actions", "qualified_actions")
    @classmethod
    def actions_unique(cls, values: list[Tier1AssistAction]) -> list[Tier1AssistAction]:
        if len(values) != len(set(values)):
            raise ValueError("Assist actions must be unique")
        return values

    @field_validator("blocking_reasons")
    @classmethod
    def blocking_reasons_safe(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("blocking reasons must be unique")
        if any(not value or len(value) > 127 for value in values):
            raise ValueError("invalid blocking reason")
        return values

    @field_validator("created_at", "expires_at")
    @classmethod
    def qualification_times_are_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("qualification timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def qualification_consistent(self) -> AssistQualificationReport:
        if self.expires_at <= self.created_at:
            raise ValueError("qualification expiry must be after creation")
        if self.qualified:
            if self.blocking_reasons:
                raise ValueError("qualified report cannot contain blocking reasons")
            if not self.qualified_actions:
                raise ValueError("qualified report requires at least one action")
            if self.test_only:
                raise ValueError("test-only evidence cannot produce a qualified report")
            if not all((
                self.runtime_artifact_sha256,
                self.model_artifact_sha256,
                self.handler_artifact_sha256,
            )):
                raise ValueError(
                    "qualified report requires fixed Runtime, model, and handler digests"
                )
        elif self.qualified_actions:
            raise ValueError("unqualified report cannot expose qualified actions")
        if not set(self.qualified_actions).issubset(self.requested_actions):
            raise ValueError("qualified actions must be a subset of requested actions")
        return self


class AssistActivationRecord(AssistModel):
    schema_version: Literal["0.6"] = ASSIST_SCHEMA_VERSION
    activation_id: str = Field(pattern=SAFE_ID_PATTERN)
    qualification_report_id: str = Field(pattern=SAFE_ID_PATTERN)
    qualification_digest: str = Field(pattern=SHA256_PATTERN)
    approver_id_hash: str = Field(pattern=SHA256_PATTERN)
    allowed_actions: list[Tier1AssistAction] = Field(min_length=1)
    max_executions_per_hour: int = Field(ge=1, le=10000)
    runtime_name: str = Field(min_length=1, max_length=96)
    runtime_version: str = Field(min_length=1, max_length=48)
    runtime_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    model_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    handler_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    model_generation: int = Field(ge=0)
    minimum_state_generation: int = Field(ge=0)
    feature_schema_hash: str = Field(pattern=SHA256_PATTERN)
    bounded_auto: Literal[False] = BOUNDED_AUTO_ENABLED
    activated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime

    @field_validator("allowed_actions")
    @classmethod
    def activation_actions_unique(cls, values: list[Tier1AssistAction]) -> list[Tier1AssistAction]:
        if len(values) != len(set(values)):
            raise ValueError("activation actions must be unique")
        return values

    @field_validator("activated_at", "expires_at")
    @classmethod
    def activation_times_are_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("activation timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def activation_expiry_valid(self) -> AssistActivationRecord:
        if self.expires_at <= self.activated_at:
            raise ValueError("activation expiry must be after activation")
        return self


class AssistRevocationRecord(AssistModel):
    schema_version: Literal["0.6"] = ASSIST_SCHEMA_VERSION
    revocation_id: str = Field(pattern=SAFE_ID_PATTERN)
    activation_id: str = Field(pattern=SAFE_ID_PATTERN)
    operator_id_hash: str = Field(pattern=SHA256_PATTERN)
    reason_code: str = Field(min_length=1, max_length=127)
    revoked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("revoked_at")
    @classmethod
    def revoked_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("revoked_at must be timezone-aware")
        return value


class AssistParserSuspensionRecord(AssistModel):
    schema_version: Literal["0.6"] = ASSIST_SCHEMA_VERSION
    suspension_id: str = Field(pattern=SAFE_ID_PATTERN)
    activation_id: str = Field(pattern=SAFE_ID_PATTERN)
    parser_id: str = Field(pattern=SAFE_ID_PATTERN)
    drift_alert_id: str = Field(pattern=SAFE_ID_PATTERN)
    operator_id_hash: str = Field(pattern=SHA256_PATTERN)
    reason_code: str = Field(min_length=1, max_length=127)
    suspended_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime

    @field_validator("suspended_at", "expires_at")
    @classmethod
    def suspension_times_are_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("suspension timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def suspension_expiry_valid(self) -> AssistParserSuspensionRecord:
        if self.expires_at <= self.suspended_at:
            raise ValueError("parser suspension expiry must be after suspension")
        return self


class AssistParserResumeRecord(AssistModel):
    schema_version: Literal["0.6"] = ASSIST_SCHEMA_VERSION
    resume_id: str = Field(pattern=SAFE_ID_PATTERN)
    suspension_id: str = Field(pattern=SAFE_ID_PATTERN)
    operator_id_hash: str = Field(pattern=SHA256_PATTERN)
    reason_code: str = Field(min_length=1, max_length=127)
    resumed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("resumed_at")
    @classmethod
    def resumed_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("resumed_at must be timezone-aware")
        return value


class AssistQueueItem(AssistModel):
    schema_version: Literal["0.6"] = ASSIST_SCHEMA_VERSION
    queue_item_id: str = Field(pattern=SAFE_ID_PATTERN)
    execution_id: str = Field(pattern=SAFE_ID_PATTERN)
    queue: AssistQueueKind
    priority: int = Field(ge=1, le=100)
    evaluation_id: str = Field(pattern=SAFE_ID_PATTERN)
    parse_run_id: str = Field(pattern=SAFE_ID_PATTERN)
    reason_codes: list[str] = Field(min_length=1)
    status: Literal["pending"] = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def queue_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class AssistExecutionRecord(AssistModel):
    schema_version: Literal["0.6"] = ASSIST_SCHEMA_VERSION
    execution_id: str = Field(pattern=SAFE_ID_PATTERN)
    activation_id: str = Field(pattern=SAFE_ID_PATTERN)
    qualification_report_id: str = Field(pattern=SAFE_ID_PATTERN)
    evaluation_id: str = Field(pattern=SAFE_ID_PATTERN)
    action: Tier1AssistAction
    status: AssistExecutionStatus
    source_run_id: str = Field(pattern=SAFE_ID_PATTERN)
    output_run_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    queue_item_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    parser_id: str | None = Field(default=None, min_length=1, max_length=127)
    reason_codes: list[str] = Field(min_length=1)
    error_code: str | None = Field(default=None, max_length=127)
    reversible: Literal[True] = True
    replaced_existing_result: Literal[False] = False
    bounded_auto: Literal[False] = BOUNDED_AUTO_ENABLED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def execution_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def outcome_consistent(self) -> AssistExecutionRecord:
        if self.status == AssistExecutionStatus.SUCCEEDED and self.error_code is not None:
            raise ValueError("successful Assist execution cannot carry an error")
        if self.status != AssistExecutionStatus.SUCCEEDED and not self.error_code:
            raise ValueError("failed or blocked Assist execution requires an error code")
        if self.action in {
            Tier1AssistAction.HUMAN_REVIEW,
            Tier1AssistAction.QUARANTINE,
        }:
            if self.status == AssistExecutionStatus.SUCCEEDED and self.queue_item_id is None:
                raise ValueError("queue action requires a queue item")
            if self.output_run_id is not None:
                raise ValueError("queue action cannot produce a parse run")
        elif self.status == AssistExecutionStatus.SUCCEEDED and self.output_run_id is None:
            raise ValueError("parser Assist action requires an output run")
        return self


class AssistAttestationRequest(AssistModel):
    feedback_id: str = Field(pattern=SAFE_ID_PATTERN)
    reviewer_role: AssistReviewerRole
    evidence_origin: AssistEvidenceOrigin
    reviewer_id_hash: str = Field(pattern=SHA256_PATTERN)
    dataset_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    approved_for_qualification: bool = False

    @model_validator(mode="after")
    def approved_request_is_strict(self) -> AssistAttestationRequest:
        if self.approved_for_qualification:
            if self.reviewer_role != AssistReviewerRole.DOMAIN_EXPERT:
                raise ValueError("qualification evidence requires a domain expert")
            if self.evidence_origin not in {
                AssistEvidenceOrigin.PRODUCTION,
                AssistEvidenceOrigin.GOLD,
                AssistEvidenceOrigin.CHALLENGE,
            }:
                raise ValueError("synthetic or unclassified evidence cannot qualify Assist")
            if self.dataset_id is None:
                raise ValueError("qualification evidence requires a dataset_id")
        return self


class AssistQualificationRequest(AssistModel):
    requested_actions: list[Tier1AssistAction] = Field(default_factory=lambda: list(TIER1_ACTIONS))


class AssistActivationRequest(AssistModel):
    qualification_report_id: str = Field(pattern=SAFE_ID_PATTERN)
    approver_id_hash: str = Field(pattern=SHA256_PATTERN)
    allowed_actions: list[Tier1AssistAction] = Field(min_length=1)
    max_executions_per_hour: int = Field(default=20, ge=1, le=10000)
    expires_at: datetime


class AssistRevocationRequest(AssistModel):
    activation_id: str = Field(pattern=SAFE_ID_PATTERN)
    operator_id_hash: str = Field(pattern=SHA256_PATTERN)
    reason_code: str = Field(min_length=1, max_length=127)


class AssistParserSuspensionRequest(AssistModel):
    activation_id: str = Field(pattern=SAFE_ID_PATTERN)
    parser_id: str = Field(pattern=SAFE_ID_PATTERN)
    drift_alert_id: str = Field(pattern=SAFE_ID_PATTERN)
    operator_id_hash: str = Field(pattern=SHA256_PATTERN)
    reason_code: str = Field(min_length=1, max_length=127)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def suspension_request_expiry_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("suspension expiry must be timezone-aware")
        return value


class AssistParserResumeRequest(AssistModel):
    suspension_id: str = Field(pattern=SAFE_ID_PATTERN)
    operator_id_hash: str = Field(pattern=SHA256_PATTERN)
    reason_code: str = Field(min_length=1, max_length=127)


class AssistExecutionRequest(AssistModel):
    activation_id: str = Field(pattern=SAFE_ID_PATTERN)
    evaluation_id: str = Field(pattern=SAFE_ID_PATTERN)


def stable_assist_id(prefix: str, *parts: str) -> str:
    material = "\0".join((prefix, *parts)).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(material).hexdigest()[:32]}"
