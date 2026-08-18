from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.schema import SAFE_ID_PATTERN, SHA256_PATTERN

PRODUCTION_SCHEMA_VERSION = "1.0"
BOUNDED_AUTO_ENABLED = False


class ProductionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    def semantic_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("created_at", None)
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


class EvidenceOrigin(StrEnum):
    REAL = "real"
    PRODUCTION_LIKE = "production-like"
    SYNTHETIC = "synthetic"


class QualificationDatasetRole(StrEnum):
    GOLD = "gold"
    CHALLENGE = "challenge"


class LicenseResolution(StrEnum):
    COMMERCIAL = "commercial-license"
    OPEN_SOURCE_COMPLIANT = "open-source-compliant"
    REPLACED = "replaced"
    UNRESOLVED = "unresolved"


class QualificationStatus(StrEnum):
    BLOCKED = "blocked"
    QUALIFIED = "qualified"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value


def _unique_safe(values: list[str], *, label: str, limit: int = 128) -> list[str]:
    if not values or len(values) > limit or len(values) != len(set(values)):
        raise ValueError(f"{label} must be non-empty, unique, and bounded")
    if any(not item or len(item) > 127 for item in values):
        raise ValueError(f"invalid {label}")
    return sorted(values)


class DatasetQualificationRequest(ProductionModel):
    dataset_name: str = Field(min_length=1, max_length=127)
    role: QualificationDatasetRole
    origin: EvidenceOrigin
    domain_families: list[str] = Field(min_length=1, max_length=64)
    document_count: int = Field(ge=1)
    page_count: int = Field(ge=1)
    modalities: list[str] = Field(min_length=1, max_length=32)
    edge_cases: list[str] = Field(min_length=1, max_length=64)
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    schema_sha256: str = Field(pattern=SHA256_PATTERN)
    content_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)
    expert_approved: bool = False
    approver_id_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    privacy_reviewed: bool = False
    license_reviewed: bool = False

    @field_validator("domain_families")
    @classmethod
    def families_valid(cls, value: list[str]) -> list[str]:
        return _unique_safe(value, label="domain families", limit=64)

    @field_validator("modalities", "edge_cases")
    @classmethod
    def labels_valid(cls, value: list[str], info: Any) -> list[str]:
        return _unique_safe(value, label=info.field_name.replace("_", " "), limit=64)

    @model_validator(mode="after")
    def approval_is_attributed(self) -> DatasetQualificationRequest:
        if self.expert_approved and self.approver_id_hash is None:
            raise ValueError("expert approval requires approver identity hash")
        return self


class DatasetQualificationEvidence(DatasetQualificationRequest):
    schema_version: Literal["1.0"] = PRODUCTION_SCHEMA_VERSION
    evidence_id: str = Field(pattern=SAFE_ID_PATTERN)
    passed: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    immutable: Literal[True] = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _created = field_validator("created_at")(_aware)


class ParserQualificationRequest(ProductionModel):
    parser_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    parser_version: str = Field(min_length=1, max_length=63)
    external: Literal[True] = True
    runtime_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    model_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    container_image_sha256: str = Field(pattern=SHA256_PATTERN)
    config_sha256: str = Field(pattern=SHA256_PATTERN)
    gold_dataset_evidence_id: str = Field(pattern=SAFE_ID_PATTERN)
    challenge_dataset_evidence_id: str = Field(pattern=SAFE_ID_PATTERN)
    accuracy: float = Field(ge=0.0, le=1.0)
    family_accuracy: dict[str, float] = Field(min_length=1, max_length=128)
    p0_errors: int = Field(ge=0)
    p1_errors: int = Field(ge=0)
    severe_error_rate: float = Field(ge=0.0, le=1.0)
    timeout_rate: float = Field(ge=0.0, le=1.0)
    failure_rate: float = Field(ge=0.0, le=1.0)
    deterministic_replay_rate: float = Field(ge=0.0, le=1.0)
    license_resolution: LicenseResolution
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("family_accuracy")
    @classmethod
    def family_accuracy_valid(cls, value: dict[str, float]) -> dict[str, float]:
        if not value or len(value) > 128:
            raise ValueError("family accuracy must be non-empty and bounded")
        for key, item in value.items():
            if not key or len(key) > 127 or not math.isfinite(item) or not 0 <= item <= 1:
                raise ValueError("invalid family accuracy")
        return dict(sorted(value.items()))


class ParserQualificationEvidence(ParserQualificationRequest):
    schema_version: Literal["1.0"] = PRODUCTION_SCHEMA_VERSION
    evidence_id: str = Field(pattern=SAFE_ID_PATTERN)
    passed: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    immutable: Literal[True] = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _created = field_validator("created_at")(_aware)


class ScaleQualificationRequest(ProductionModel):
    workload_profile: str = Field(min_length=1, max_length=127)
    environment_sha256: str = Field(pattern=SHA256_PATTERN)
    source_commit_sha: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    duration_hours: float = Field(gt=0.0, le=24 * 365)
    max_concurrency: int = Field(ge=1, le=100000)
    document_count: int = Field(ge=1)
    page_count: int = Field(ge=1)
    latency_ms_p95: float = Field(ge=0.0)
    latency_ms_p99: float = Field(ge=0.0)
    peak_rss_mb: float = Field(ge=0.0)
    peak_disk_mb: float = Field(ge=0.0)
    error_rate: float = Field(ge=0.0, le=1.0)
    duplicate_side_effects: int = Field(ge=0)
    restart_recovery_passed: bool
    idempotency_passed: bool
    disk_full_recovery_passed: bool
    corrupted_record_detection_passed: bool
    index_rebuild_passed: bool
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def latency_order(self) -> ScaleQualificationRequest:
        if self.latency_ms_p99 < self.latency_ms_p95:
            raise ValueError("p99 latency cannot be lower than p95")
        return self


class ScaleQualificationEvidence(ScaleQualificationRequest):
    schema_version: Literal["1.0"] = PRODUCTION_SCHEMA_VERSION
    evidence_id: str = Field(pattern=SAFE_ID_PATTERN)
    passed: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    immutable: Literal[True] = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _created = field_validator("created_at")(_aware)


class SupplyChainQualificationRequest(ProductionModel):
    source_commit_sha: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    ci_provider: str = Field(min_length=1, max_length=127)
    ci_run_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    ruff_passed: bool
    mypy_passed: bool
    tests_passed: bool
    test_count: int = Field(ge=1)
    branch_coverage: float = Field(ge=0.0, le=100.0)
    sbom_sha256: str = Field(pattern=SHA256_PATTERN)
    vulnerability_scan_sha256: str = Field(pattern=SHA256_PATTERN)
    critical_vulnerabilities: int = Field(ge=0)
    high_vulnerabilities: int = Field(ge=0)
    license_scan_sha256: str = Field(pattern=SHA256_PATTERN)
    container_image_sha256: str = Field(pattern=SHA256_PATTERN)
    reproducible_build_passed: bool
    release_signature_verified: bool
    release_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)


class SupplyChainQualificationEvidence(SupplyChainQualificationRequest):
    schema_version: Literal["1.0"] = PRODUCTION_SCHEMA_VERSION
    evidence_id: str = Field(pattern=SAFE_ID_PATTERN)
    passed: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    immutable: Literal[True] = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _created = field_validator("created_at")(_aware)


class LicenseQualificationRequest(ProductionModel):
    component: str = Field(min_length=1, max_length=127)
    resolution: LicenseResolution
    distribution_mode: str = Field(min_length=1, max_length=127)
    license_name: str = Field(min_length=1, max_length=127)
    legal_reviewed: bool
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)


class LicenseQualificationEvidence(LicenseQualificationRequest):
    schema_version: Literal["1.0"] = PRODUCTION_SCHEMA_VERSION
    evidence_id: str = Field(pattern=SAFE_ID_PATTERN)
    passed: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    immutable: Literal[True] = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _created = field_validator("created_at")(_aware)


class PilotQualificationRequest(ProductionModel):
    pilot_name: str = Field(min_length=1, max_length=127)
    origin: EvidenceOrigin
    domain_families: list[str] = Field(min_length=1, max_length=64)
    duration_days: float = Field(gt=0.0, le=3650)
    document_count: int = Field(ge=1)
    expert_reviewed_count: int = Field(ge=1)
    accuracy: float = Field(ge=0.0, le=1.0)
    p0_errors: int = Field(ge=0)
    p1_errors: int = Field(ge=0)
    severe_error_rate: float = Field(ge=0.0, le=1.0)
    human_edit_seconds_p95: float = Field(ge=0.0)
    rollback_drill_passed: bool
    incident_count: int = Field(ge=0)
    unresolved_high_severity_incidents: int = Field(ge=0)
    evidence_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("domain_families")
    @classmethod
    def pilot_families_valid(cls, value: list[str]) -> list[str]:
        return _unique_safe(value, label="pilot domain families", limit=64)

    @model_validator(mode="after")
    def reviewed_not_over_total(self) -> PilotQualificationRequest:
        if self.expert_reviewed_count > self.document_count:
            raise ValueError("expert reviewed count cannot exceed document count")
        return self


class PilotQualificationEvidence(PilotQualificationRequest):
    schema_version: Literal["1.0"] = PRODUCTION_SCHEMA_VERSION
    evidence_id: str = Field(pattern=SAFE_ID_PATTERN)
    passed: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    immutable: Literal[True] = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _created = field_validator("created_at")(_aware)


class ProductionQualificationRequest(ProductionModel):
    dataset_evidence_ids: list[str] = Field(min_length=2, max_length=64)
    parser_evidence_ids: list[str] = Field(min_length=1, max_length=32)
    scale_evidence_id: str = Field(pattern=SAFE_ID_PATTERN)
    supply_chain_evidence_id: str = Field(pattern=SAFE_ID_PATTERN)
    license_evidence_ids: list[str] = Field(min_length=1, max_length=32)
    pilot_evidence_id: str = Field(pattern=SAFE_ID_PATTERN)
    requested_by_id_hash: str = Field(pattern=SHA256_PATTERN)

    @field_validator("dataset_evidence_ids", "parser_evidence_ids", "license_evidence_ids")
    @classmethod
    def ids_unique(cls, value: list[str], info: Any) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError(f"{info.field_name} must be unique")
        return sorted(value)


class ProductionQualificationReport(ProductionQualificationRequest):
    schema_version: Literal["1.0"] = PRODUCTION_SCHEMA_VERSION
    report_id: str = Field(pattern=SAFE_ID_PATTERN)
    policy_sha256: str = Field(pattern=SHA256_PATTERN)
    status: QualificationStatus
    qualified: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    automatic_release_authorized: Literal[False] = False
    human_release_required: Literal[True] = True
    bounded_auto: Literal[False] = False
    immutable: Literal[True] = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _created = field_validator("created_at")(_aware)

    @model_validator(mode="after")
    def status_matches(self) -> ProductionQualificationReport:
        if self.qualified != (self.status == QualificationStatus.QUALIFIED):
            raise ValueError("qualification status does not match qualified flag")
        if self.qualified and self.blocking_reasons:
            raise ValueError("qualified report cannot contain blocking reasons")
        if not self.qualified and not self.blocking_reasons:
            raise ValueError("blocked report requires blocking reasons")
        return self


def stable_production_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}-{digest}"
