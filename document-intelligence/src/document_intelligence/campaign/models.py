from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.schema import SAFE_ID_PATTERN, SHA256_PATTERN

CAMPAIGN_SCHEMA_VERSION = "1.0"
CAMPAIGN_BUNDLE_FORMAT_VERSION = 1


class CampaignModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    def semantic_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("created_at", None)
        payload.pop("event_id", None)
        payload.pop("sequence", None)
        payload.pop("previous_event_sha256", None)
        return payload

    def semantic_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.semantic_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()


class CampaignStepKind(StrEnum):
    GOLD_DATASET = "gold-dataset"
    CHALLENGE_DATASET = "challenge-dataset"
    PARSER_QUALIFICATION = "parser-qualification"
    SCALE_SOAK = "scale-soak"
    SUPPLY_CHAIN = "supply-chain"
    LICENSE_REVIEW = "license-review"
    PILOT = "pilot"
    QUALIFICATION_REPORT = "qualification-report"


class CampaignState(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CampaignStepState(StrEnum):
    PENDING = "pending"
    LEASED = "leased"
    COMPLETED = "completed"
    FAILED = "failed"


class CampaignAction(StrEnum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    CLAIM_STEP = "claim-step"
    HEARTBEAT = "heartbeat"
    LINK_EVIDENCE = "link-evidence"
    CHECKPOINT = "checkpoint"
    COMPLETE_STEP = "complete-step"
    FAIL_STEP = "fail-step"
    RETRY_STEP = "retry-step"
    FINALIZE = "finalize"


class CampaignEvidenceKind(StrEnum):
    DATASET = "dataset"
    PARSER = "parser"
    SCALE = "scale"
    SUPPLY_CHAIN = "supply-chain"
    LICENSE = "license"
    PILOT = "pilot"
    REPORT = "report"


STEP_EVIDENCE_KIND: dict[CampaignStepKind, CampaignEvidenceKind] = {
    CampaignStepKind.GOLD_DATASET: CampaignEvidenceKind.DATASET,
    CampaignStepKind.CHALLENGE_DATASET: CampaignEvidenceKind.DATASET,
    CampaignStepKind.PARSER_QUALIFICATION: CampaignEvidenceKind.PARSER,
    CampaignStepKind.SCALE_SOAK: CampaignEvidenceKind.SCALE,
    CampaignStepKind.SUPPLY_CHAIN: CampaignEvidenceKind.SUPPLY_CHAIN,
    CampaignStepKind.LICENSE_REVIEW: CampaignEvidenceKind.LICENSE,
    CampaignStepKind.PILOT: CampaignEvidenceKind.PILOT,
    CampaignStepKind.QUALIFICATION_REPORT: CampaignEvidenceKind.REPORT,
}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value


class CampaignStepSpec(CampaignModel):
    step_id: str = Field(pattern=SAFE_ID_PATTERN)
    kind: CampaignStepKind
    depends_on: list[str] = Field(default_factory=list, max_length=32)
    minimum_evidence_count: int = Field(default=1, ge=1, le=64)
    required: bool = True

    @field_validator("depends_on")
    @classmethod
    def dependency_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("step dependencies must be unique")
        for item in value:
            if not item or len(item) > 127:
                raise ValueError("invalid step dependency")
        return sorted(value)


class CampaignCreateRequest(CampaignModel):
    campaign_name: str = Field(min_length=1, max_length=127)
    source_commit_sha: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    environment_sha256: str = Field(pattern=SHA256_PATTERN)
    policy_sha256: str = Field(pattern=SHA256_PATTERN)
    created_by_id_hash: str = Field(pattern=SHA256_PATTERN)
    steps: list[CampaignStepSpec] = Field(min_length=1, max_length=64)
    external_data_authorized: bool = False
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_graph(self) -> CampaignCreateRequest:
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("campaign step ids must be unique")
        known = set(ids)
        for step in self.steps:
            if step.step_id in step.depends_on or not set(step.depends_on).issubset(known):
                raise ValueError("campaign step dependency is invalid")
        visiting: set[str] = set()
        visited: set[str] = set()
        graph = {step.step_id: step.depends_on for step in self.steps}

        def walk(node: str) -> None:
            if node in visiting:
                raise ValueError("campaign step graph contains a cycle")
            if node in visited:
                return
            visiting.add(node)
            for parent in graph[node]:
                walk(parent)
            visiting.remove(node)
            visited.add(node)

        for item in ids:
            walk(item)
        report_steps = [
            step
            for step in self.steps
            if step.kind == CampaignStepKind.QUALIFICATION_REPORT
        ]
        if len(report_steps) != 1:
            raise ValueError("campaign requires exactly one qualification report step")
        return self


class CampaignManifest(CampaignCreateRequest):
    schema_version: Literal["1.0"] = CAMPAIGN_SCHEMA_VERSION
    campaign_id: str = Field(pattern=SAFE_ID_PATTERN)
    automatic_release_authorized: Literal[False] = False
    bounded_auto: Literal[False] = False
    immutable: Literal[True] = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _created = field_validator("created_at")(_aware)


class StepClaimRequest(CampaignModel):
    worker_id_hash: str = Field(pattern=SHA256_PATTERN)
    lease_seconds: int = Field(default=900, ge=30, le=604800)


class StepHeartbeatRequest(CampaignModel):
    worker_id_hash: str = Field(pattern=SHA256_PATTERN)
    lease_id: str = Field(pattern=SAFE_ID_PATTERN)
    lease_seconds: int = Field(default=900, ge=30, le=604800)


class EvidenceLinkRequest(CampaignModel):
    worker_id_hash: str = Field(pattern=SHA256_PATTERN)
    lease_id: str = Field(pattern=SAFE_ID_PATTERN)
    evidence_kind: CampaignEvidenceKind
    evidence_id: str = Field(pattern=SAFE_ID_PATTERN)


class StepCheckpointRequest(CampaignModel):
    worker_id_hash: str = Field(pattern=SHA256_PATTERN)
    lease_id: str = Field(pattern=SAFE_ID_PATTERN)
    completed_units: int = Field(ge=0)
    total_units: int = Field(ge=1)
    cursor_sha256: str = Field(pattern=SHA256_PATTERN)
    metrics: dict[str, float] = Field(default_factory=dict, max_length=64)

    @field_validator("metrics")
    @classmethod
    def metrics_finite(cls, value: dict[str, float]) -> dict[str, float]:
        for key, item in value.items():
            if not key or len(key) > 127 or not math.isfinite(item):
                raise ValueError("checkpoint metrics must be finite and bounded")
        return dict(sorted(value.items()))

    @model_validator(mode="after")
    def progress_valid(self) -> StepCheckpointRequest:
        if self.completed_units > self.total_units:
            raise ValueError("completed units cannot exceed total units")
        return self


class StepTransitionRequest(CampaignModel):
    worker_id_hash: str = Field(pattern=SHA256_PATTERN)
    lease_id: str = Field(pattern=SAFE_ID_PATTERN)
    note: str | None = Field(default=None, max_length=2000)


class CampaignActorRequest(CampaignModel):
    actor_id_hash: str = Field(pattern=SHA256_PATTERN)
    note: str | None = Field(default=None, max_length=2000)


class CampaignFinalizeRequest(CampaignModel):
    actor_id_hash: str = Field(pattern=SHA256_PATTERN)
    requested_by_id_hash: str = Field(pattern=SHA256_PATTERN)


class CampaignEvent(CampaignModel):
    schema_version: Literal["1.0"] = CAMPAIGN_SCHEMA_VERSION
    event_id: str = Field(pattern=SAFE_ID_PATTERN)
    campaign_id: str = Field(pattern=SAFE_ID_PATTERN)
    sequence: int = Field(ge=1)
    previous_event_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    action: CampaignAction
    actor_id_hash: str = Field(pattern=SHA256_PATTERN)
    step_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    worker_id_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    lease_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    lease_expires_at: datetime | None = None
    evidence_kind: CampaignEvidenceKind | None = None
    evidence_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    evidence_semantic_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    checkpoint: StepCheckpointRequest | None = None
    note: str | None = Field(default=None, max_length=2000)
    immutable: Literal[True] = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _created = field_validator("created_at")(_aware)
    _lease_expiry = field_validator("lease_expires_at")(_aware)

    @model_validator(mode="after")
    def shape_for_action(self) -> CampaignEvent:
        step_actions = {
            CampaignAction.CLAIM_STEP,
            CampaignAction.HEARTBEAT,
            CampaignAction.LINK_EVIDENCE,
            CampaignAction.CHECKPOINT,
            CampaignAction.COMPLETE_STEP,
            CampaignAction.FAIL_STEP,
            CampaignAction.RETRY_STEP,
        }
        if self.action in step_actions and self.step_id is None:
            raise ValueError("step action requires step id")
        if self.action in {CampaignAction.CLAIM_STEP, CampaignAction.HEARTBEAT}:
            if not self.worker_id_hash or not self.lease_id or not self.lease_expires_at:
                raise ValueError("lease action requires worker, lease id, and expiry")
        if self.action in {
            CampaignAction.LINK_EVIDENCE,
            CampaignAction.CHECKPOINT,
            CampaignAction.COMPLETE_STEP,
            CampaignAction.FAIL_STEP,
        } and (not self.worker_id_hash or not self.lease_id):
            raise ValueError("worker action requires worker and lease id")
        if self.action == CampaignAction.LINK_EVIDENCE:
            if not self.evidence_kind or not self.evidence_id or not self.evidence_semantic_sha256:
                raise ValueError("evidence link requires evidence identity and digest")
        if self.action == CampaignAction.CHECKPOINT and self.checkpoint is None:
            raise ValueError("checkpoint action requires checkpoint payload")
        if self.action == CampaignAction.FINALIZE:
            if (
                self.step_id is None
                or self.evidence_kind != CampaignEvidenceKind.REPORT
                or self.evidence_id is None
                or self.evidence_semantic_sha256 is None
            ):
                raise ValueError("finalize action requires qualification report evidence")
        return self

    def chain_digest(self) -> str:
        return hashlib.sha256(self.model_dump_json(exclude_none=False).encode("utf-8")).hexdigest()


class EvidenceLink(CampaignModel):
    step_id: str = Field(pattern=SAFE_ID_PATTERN)
    evidence_kind: CampaignEvidenceKind
    evidence_id: str = Field(pattern=SAFE_ID_PATTERN)
    evidence_semantic_sha256: str = Field(pattern=SHA256_PATTERN)
    passed: bool


class StepLease(CampaignModel):
    lease_id: str = Field(pattern=SAFE_ID_PATTERN)
    worker_id_hash: str = Field(pattern=SHA256_PATTERN)
    expires_at: datetime

    _expires = field_validator("expires_at")(_aware)


class CampaignStepSnapshot(CampaignModel):
    step_id: str = Field(pattern=SAFE_ID_PATTERN)
    kind: CampaignStepKind
    state: CampaignStepState
    depends_on: list[str]
    evidence: list[EvidenceLink] = Field(default_factory=list)
    lease: StepLease | None = None
    checkpoint: StepCheckpointRequest | None = None
    failure_note: str | None = None


class CampaignSnapshot(CampaignModel):
    schema_version: Literal["1.0"] = CAMPAIGN_SCHEMA_VERSION
    campaign_id: str = Field(pattern=SAFE_ID_PATTERN)
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    state: CampaignState
    steps: list[CampaignStepSnapshot]
    event_count: int = Field(ge=0)
    last_event_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    production_report_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    production_qualified: bool = False
    automatic_release_authorized: Literal[False] = False
    bounded_auto: Literal[False] = False


class CampaignBundleManifest(CampaignModel):
    format_version: Literal[1] = CAMPAIGN_BUNDLE_FORMAT_VERSION
    bundle_id: str = Field(pattern=SAFE_ID_PATTERN)
    campaign_id: str = Field(pattern=SAFE_ID_PATTERN)
    campaign_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    event_chain_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    files: dict[str, str] = Field(min_length=2, max_length=512)
    contains_raw_documents: Literal[False] = False
    automatic_release_authorized: Literal[False] = False
    bounded_auto: Literal[False] = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _created = field_validator("created_at")(_aware)

    @field_validator("files")
    @classmethod
    def files_valid(cls, value: dict[str, str]) -> dict[str, str]:
        for path, digest in value.items():
            if path.startswith("/") or ".." in path.split("/") or "\\" in path:
                raise ValueError("bundle file path is unsafe")
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("bundle file digest is invalid")
        return dict(sorted(value.items()))


def stable_campaign_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}-{digest}"
