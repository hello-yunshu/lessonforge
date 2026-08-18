from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.schema import SAFE_ID_PATTERN, SHA256_PATTERN

MLOPS_SCHEMA_VERSION = "0.7"
BOUNDED_AUTO_ENABLED = False
GIT_REV_PATTERN = r"^[0-9a-f]{7,64}$"


class MLOpsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    def semantic_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        for field in (
            "created_at",
            "selected_at",
            "approved_at",
            "deployed_at",
            "rolled_back_at",
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


class DatasetRole(StrEnum):
    TRAIN = "train"
    VALIDATION = "validation"
    GOLD = "gold"
    CHALLENGE = "challenge"


class ModelAlias(StrEnum):
    CANDIDATE = "candidate"
    SHADOW = "shadow"
    CHAMPION = "champion"
    ROLLBACK = "rollback"


class ExperimentStatus(StrEnum):
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    KILLED = "KILLED"


class ActiveLearningSelection(MLOpsModel):
    evaluation_id: str = Field(pattern=SAFE_ID_PATTERN)
    parse_run_id: str = Field(pattern=SAFE_ID_PATTERN)
    document_family: str = Field(default="unknown", min_length=1, max_length=127)
    score: float = Field(ge=0.0, le=100.0)
    reason_codes: list[str] = Field(min_length=1, max_length=32)

    @field_validator("reason_codes")
    @classmethod
    def reasons_are_safe(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("active-learning reasons must be unique")
        if any(
            not value
            or len(value) > 127
            or not all(character.isalnum() or character in "_-" for character in value)
            for value in values
        ):
            raise ValueError("invalid active-learning reason")
        return values


class ActiveLearningBatch(MLOpsModel):
    schema_version: Literal["0.7"] = MLOPS_SCHEMA_VERSION
    batch_id: str = Field(pattern=SAFE_ID_PATTERN)
    policy_version: str = Field(min_length=1, max_length=127)
    source_digest: str = Field(pattern=SHA256_PATTERN)
    max_items: int = Field(ge=1, le=10000)
    max_per_family: int = Field(ge=1, le=10000)
    selections: list[ActiveLearningSelection]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def created_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def selection_limits_hold(self) -> ActiveLearningBatch:
        if len(self.selections) > self.max_items:
            raise ValueError("active-learning batch exceeds max_items")
        ids = [item.evaluation_id for item in self.selections]
        if len(ids) != len(set(ids)):
            raise ValueError("active-learning batch contains duplicate evaluations")
        counts: dict[str, int] = {}
        for item in self.selections:
            counts[item.document_family] = counts.get(item.document_family, 0) + 1
        if any(value > self.max_per_family for value in counts.values()):
            raise ValueError("active-learning batch exceeds family diversity cap")
        return self


class DatasetSnapshot(MLOpsModel):
    schema_version: Literal["0.7"] = MLOPS_SCHEMA_VERSION
    snapshot_id: str = Field(pattern=SAFE_ID_PATTERN)
    role: DatasetRole
    dataset_name: str = Field(min_length=1, max_length=127)
    dvc_repo_revision: str = Field(pattern=GIT_REV_PATTERN)
    dvc_data_hash: str = Field(pattern=SHA256_PATTERN)
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    schema_sha256: str = Field(pattern=SHA256_PATTERN)
    source_commit_sha: str = Field(pattern=GIT_REV_PATTERN)
    record_count: int = Field(ge=1)
    file_count: int = Field(ge=1)
    parent_snapshot_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    expert_approved: bool = False
    approver_id_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    immutable: Literal[True] = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def snapshot_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def protected_sets_need_expert_approval(self) -> DatasetSnapshot:
        if self.role in {DatasetRole.GOLD, DatasetRole.CHALLENGE}:
            if not self.expert_approved or self.approver_id_hash is None:
                raise ValueError("gold and challenge snapshots require expert approval")
        if self.expert_approved and self.approver_id_hash is None:
            raise ValueError("expert-approved snapshot requires approver identity hash")
        return self


class MLflowRunRecord(MLOpsModel):
    schema_version: Literal["0.7"] = MLOPS_SCHEMA_VERSION
    record_id: str = Field(pattern=SAFE_ID_PATTERN)
    experiment_id: str = Field(min_length=1, max_length=127)
    run_id: str = Field(min_length=1, max_length=127)
    tracking_uri_sha256: str = Field(pattern=SHA256_PATTERN)
    artifact_uri_sha256: str = Field(pattern=SHA256_PATTERN)
    source_commit_sha: str = Field(pattern=GIT_REV_PATTERN)
    params_sha256: str = Field(pattern=SHA256_PATTERN)
    model_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    dataset_snapshot_ids: list[str] = Field(min_length=1, max_length=64)
    metrics: dict[str, float] = Field(default_factory=dict)
    status: ExperimentStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("dataset_snapshot_ids")
    @classmethod
    def snapshots_are_unique_and_safe(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("MLflow run contains duplicate dataset snapshots")
        for value in values:
            if not value or len(value) > 127:
                raise ValueError("invalid dataset snapshot id")
        return values

    @field_validator("metrics")
    @classmethod
    def metrics_are_finite_and_bounded(cls, value: dict[str, float]) -> dict[str, float]:
        if len(value) > 256:
            raise ValueError("too many MLflow metrics")
        for key, item in value.items():
            if not key or len(key) > 127 or not math.isfinite(item):
                raise ValueError("invalid MLflow metric")
        return value

    @field_validator("created_at")
    @classmethod
    def run_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class ModelCandidate(MLOpsModel):
    schema_version: Literal["0.7"] = MLOPS_SCHEMA_VERSION
    candidate_id: str = Field(pattern=SAFE_ID_PATTERN)
    model_family: str = Field(min_length=1, max_length=127)
    model_version: str = Field(min_length=1, max_length=48)
    model_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    source_commit_sha: str = Field(pattern=GIT_REV_PATTERN)
    mlflow_record_id: str = Field(pattern=SAFE_ID_PATTERN)
    train_snapshot_id: str = Field(pattern=SAFE_ID_PATTERN)
    validation_snapshot_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    baseline_candidate_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    candidate_only: Literal[True] = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def candidate_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class MetricSet(MLOpsModel):
    accuracy: float = Field(ge=0.0, le=1.0)
    p0_errors: int = Field(ge=0)
    p1_errors: int = Field(ge=0)
    severe_error_rate: float = Field(ge=0.0, le=1.0)
    standard_mismatch_rate: float = Field(ge=0.0, le=1.0)
    key_value_accuracy: float = Field(ge=0.0, le=1.0)
    relation_accuracy: float = Field(ge=0.0, le=1.0)
    latency_ms_p95: float = Field(ge=0.0)
    cost_usd_per_document: float = Field(ge=0.0)
    family_accuracy: dict[str, float] = Field(default_factory=dict)

    @field_validator("family_accuracy")
    @classmethod
    def family_metrics_are_valid(cls, value: dict[str, float]) -> dict[str, float]:
        if len(value) > 256:
            raise ValueError("too many document-family metrics")
        for key, item in value.items():
            if not key or len(key) > 127 or not 0.0 <= item <= 1.0:
                raise ValueError("invalid document-family metric")
        return value


class CandidateEvaluationReport(MLOpsModel):
    schema_version: Literal["0.7"] = MLOPS_SCHEMA_VERSION
    report_id: str = Field(pattern=SAFE_ID_PATTERN)
    candidate_id: str = Field(pattern=SAFE_ID_PATTERN)
    baseline_candidate_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    gold_snapshot_id: str = Field(pattern=SAFE_ID_PATTERN)
    challenge_snapshot_id: str = Field(pattern=SAFE_ID_PATTERN)
    candidate_gold: MetricSet
    candidate_challenge: MetricSet
    baseline_gold: MetricSet | None = None
    baseline_challenge: MetricSet | None = None
    evaluator_version: str = Field(min_length=1, max_length=127)
    evaluation_config_sha256: str = Field(pattern=SHA256_PATTERN)
    reproducibility_sha256: str = Field(pattern=SHA256_PATTERN)
    minimum_accuracy: float = Field(ge=0.0, le=1.0)
    minimum_challenge_improvement: float = Field(ge=0.0, le=1.0)
    maximum_latency_ms_p95: float = Field(gt=0.0)
    maximum_cost_usd_per_document: float = Field(ge=0.0)
    maximum_family_regression: float = Field(ge=0.0, le=1.0)
    passed: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("blocking_reasons")
    @classmethod
    def blocks_are_unique_and_safe(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("evaluation blocking reasons must be unique")
        if any(not value or len(value) > 127 for value in values):
            raise ValueError("invalid evaluation blocking reason")
        return values

    @field_validator("created_at")
    @classmethod
    def evaluation_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def outcome_matches_reasons(self) -> CandidateEvaluationReport:
        if self.passed and self.blocking_reasons:
            raise ValueError("passed evaluation cannot contain blocking reasons")
        if not self.passed and not self.blocking_reasons:
            raise ValueError("failed evaluation requires blocking reasons")
        if self.baseline_candidate_id is None:
            if self.baseline_gold is not None or self.baseline_challenge is not None:
                raise ValueError("baseline metrics require a baseline candidate")
        elif self.baseline_gold is None or self.baseline_challenge is None:
            raise ValueError("baseline candidate requires gold and challenge metrics")
        return self


class ShadowValidationReport(MLOpsModel):
    schema_version: Literal["0.7"] = MLOPS_SCHEMA_VERSION
    report_id: str = Field(pattern=SAFE_ID_PATTERN)
    candidate_id: str = Field(pattern=SAFE_ID_PATTERN)
    evaluation_report_id: str = Field(pattern=SAFE_ID_PATTERN)
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)
    sample_count: int = Field(ge=1)
    accuracy: float = Field(ge=0.0, le=1.0)
    p0_errors: int = Field(ge=0)
    p1_errors: int = Field(ge=0)
    severe_error_rate: float = Field(ge=0.0, le=1.0)
    latency_ms_p95: float = Field(ge=0.0)
    cost_usd_per_document: float = Field(ge=0.0)
    active_drift_alerts: int = Field(ge=0)
    started_at: datetime
    ended_at: datetime
    passed: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("started_at", "ended_at", "created_at")
    @classmethod
    def shadow_times_are_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Shadow validation timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def shadow_validation_is_consistent(self) -> ShadowValidationReport:
        if self.ended_at <= self.started_at:
            raise ValueError("Shadow validation end must be after start")
        if self.passed and self.blocking_reasons:
            raise ValueError("passed Shadow validation cannot contain blockers")
        if not self.passed and not self.blocking_reasons:
            raise ValueError("failed Shadow validation requires blockers")
        return self


class ReleaseApproval(MLOpsModel):
    schema_version: Literal["0.7"] = MLOPS_SCHEMA_VERSION
    approval_id: str = Field(pattern=SAFE_ID_PATTERN)
    candidate_id: str = Field(pattern=SAFE_ID_PATTERN)
    evaluation_report_id: str = Field(pattern=SAFE_ID_PATTERN)
    shadow_validation_report_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    approver_id_hash: str = Field(pattern=SHA256_PATTERN)
    approver_role: Literal["release_manager", "domain_expert"]
    approved: Literal[True] = True
    reason_code: str = Field(min_length=1, max_length=127)
    approved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("approved_at")
    @classmethod
    def approval_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("approved_at must be timezone-aware")
        return value


class AliasUpdateRecord(MLOpsModel):
    schema_version: Literal["0.7"] = MLOPS_SCHEMA_VERSION
    update_id: str = Field(pattern=SAFE_ID_PATTERN)
    alias: ModelAlias
    candidate_id: str = Field(pattern=SAFE_ID_PATTERN)
    previous_candidate_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    evaluation_report_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    approval_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    operator_id_hash: str = Field(pattern=SHA256_PATTERN)
    reason_code: str = Field(min_length=1, max_length=127)
    deployed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("deployed_at")
    @classmethod
    def deployment_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("deployed_at must be timezone-aware")
        return value


class RollbackRecord(MLOpsModel):
    schema_version: Literal["0.7"] = MLOPS_SCHEMA_VERSION
    rollback_id: str = Field(pattern=SAFE_ID_PATTERN)
    from_candidate_id: str = Field(pattern=SAFE_ID_PATTERN)
    to_candidate_id: str = Field(pattern=SAFE_ID_PATTERN)
    operator_id_hash: str = Field(pattern=SHA256_PATTERN)
    reason_code: str = Field(min_length=1, max_length=127)
    alias_update_id: str = Field(pattern=SAFE_ID_PATTERN)
    rolled_back_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("rolled_back_at")
    @classmethod
    def rollback_time_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("rolled_back_at must be timezone-aware")
        return value


class DatasetSnapshotRequest(MLOpsModel):
    role: DatasetRole
    dataset_name: str = Field(min_length=1, max_length=127)
    dvc_repo_revision: str = Field(pattern=GIT_REV_PATTERN)
    dvc_data_hash: str = Field(pattern=SHA256_PATTERN)
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    schema_sha256: str = Field(pattern=SHA256_PATTERN)
    source_commit_sha: str = Field(pattern=GIT_REV_PATTERN)
    record_count: int = Field(ge=1)
    file_count: int = Field(ge=1)
    parent_snapshot_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    expert_approved: bool = False
    approver_id_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)


class MLflowRunRequest(MLOpsModel):
    experiment_id: str = Field(min_length=1, max_length=127)
    run_id: str = Field(min_length=1, max_length=127)
    tracking_uri_sha256: str = Field(pattern=SHA256_PATTERN)
    artifact_uri_sha256: str = Field(pattern=SHA256_PATTERN)
    source_commit_sha: str = Field(pattern=GIT_REV_PATTERN)
    params_sha256: str = Field(pattern=SHA256_PATTERN)
    model_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    dataset_snapshot_ids: list[str] = Field(min_length=1, max_length=64)
    metrics: dict[str, float] = Field(default_factory=dict)
    status: ExperimentStatus

    @field_validator("dataset_snapshot_ids")
    @classmethod
    def request_snapshots_are_unique_and_safe(cls, values: list[str]) -> list[str]:
        return MLflowRunRecord.snapshots_are_unique_and_safe(values)

    @field_validator("metrics")
    @classmethod
    def request_metrics_are_finite_and_bounded(
        cls, value: dict[str, float]
    ) -> dict[str, float]:
        return MLflowRunRecord.metrics_are_finite_and_bounded(value)


class CandidateRegistrationRequest(MLOpsModel):
    model_family: str = Field(min_length=1, max_length=127)
    model_version: str = Field(min_length=1, max_length=48)
    model_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    source_commit_sha: str = Field(pattern=GIT_REV_PATTERN)
    mlflow_record_id: str = Field(pattern=SAFE_ID_PATTERN)
    train_snapshot_id: str = Field(pattern=SAFE_ID_PATTERN)
    validation_snapshot_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    baseline_candidate_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)


class EvaluationRequest(MLOpsModel):
    candidate_id: str = Field(pattern=SAFE_ID_PATTERN)
    baseline_candidate_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    gold_snapshot_id: str = Field(pattern=SAFE_ID_PATTERN)
    challenge_snapshot_id: str = Field(pattern=SAFE_ID_PATTERN)
    candidate_gold: MetricSet
    candidate_challenge: MetricSet
    baseline_gold: MetricSet | None = None
    baseline_challenge: MetricSet | None = None
    evaluator_version: str = Field(min_length=1, max_length=127)
    evaluation_config_sha256: str = Field(pattern=SHA256_PATTERN)
    reproducibility_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def request_baseline_is_consistent(self) -> EvaluationRequest:
        if self.baseline_candidate_id is None:
            if self.baseline_gold is not None or self.baseline_challenge is not None:
                raise ValueError("baseline metrics require a baseline candidate")
        elif self.baseline_gold is None or self.baseline_challenge is None:
            raise ValueError("baseline candidate requires gold and challenge metrics")
        return self


class ShadowValidationRequest(MLOpsModel):
    candidate_id: str = Field(pattern=SAFE_ID_PATTERN)
    evaluation_report_id: str = Field(pattern=SAFE_ID_PATTERN)
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)
    sample_count: int = Field(ge=1)
    accuracy: float = Field(ge=0.0, le=1.0)
    p0_errors: int = Field(ge=0)
    p1_errors: int = Field(ge=0)
    severe_error_rate: float = Field(ge=0.0, le=1.0)
    latency_ms_p95: float = Field(ge=0.0)
    cost_usd_per_document: float = Field(ge=0.0)
    active_drift_alerts: int = Field(ge=0)
    started_at: datetime
    ended_at: datetime

    @field_validator("started_at", "ended_at")
    @classmethod
    def request_shadow_times_are_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Shadow validation timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def request_shadow_window_is_valid(self) -> ShadowValidationRequest:
        if self.ended_at <= self.started_at:
            raise ValueError("Shadow validation end must be after start")
        return self


class ApprovalRequest(MLOpsModel):
    candidate_id: str = Field(pattern=SAFE_ID_PATTERN)
    evaluation_report_id: str = Field(pattern=SAFE_ID_PATTERN)
    shadow_validation_report_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    approver_id_hash: str = Field(pattern=SHA256_PATTERN)
    approver_role: Literal["release_manager", "domain_expert"]
    reason_code: str = Field(min_length=1, max_length=127)


class PromoteRequest(MLOpsModel):
    candidate_id: str = Field(pattern=SAFE_ID_PATTERN)
    evaluation_report_id: str = Field(pattern=SAFE_ID_PATTERN)
    shadow_validation_report_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    approval_id: str = Field(pattern=SAFE_ID_PATTERN)
    operator_id_hash: str = Field(pattern=SHA256_PATTERN)
    reason_code: str = Field(min_length=1, max_length=127)


class RollbackRequest(MLOpsModel):
    operator_id_hash: str = Field(pattern=SHA256_PATTERN)
    reason_code: str = Field(min_length=1, max_length=127)


def stable_mlops_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}-{digest}"
