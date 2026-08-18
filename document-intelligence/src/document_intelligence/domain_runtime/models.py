from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.schema import (
    SAFE_ID_PATTERN,
    SHA256_PATTERN,
    ReviewStatus,
    validate_safe_id,
)

DOMAIN_RESULT_SCHEMA_VERSION = "1.0"


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DomainExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FALLBACK_GENERIC = "fallback_generic"


class DomainAnnotation(DomainModel):
    annotation_id: str = Field(pattern=SAFE_ID_PATTERN)
    element_id: str = Field(pattern=SAFE_ID_PATTERN)
    domain_type: str = Field(min_length=1, max_length=127)
    properties: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(min_length=1)
    rule_id: str = Field(pattern=SAFE_ID_PATTERN)
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED

    @field_validator("evidence_ids")
    @classmethod
    def valid_evidence_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            validate_safe_id(value, field_name="evidence_id")
        if len(values) != len(set(values)):
            raise ValueError("domain annotation evidence IDs contain duplicates")
        return values


class DomainRelationAnnotation(DomainModel):
    relation_id: str = Field(pattern=SAFE_ID_PATTERN)
    source_id: str = Field(pattern=SAFE_ID_PATTERN)
    target_id: str = Field(pattern=SAFE_ID_PATTERN)
    domain_type: str = Field(min_length=1, max_length=127)
    base_relation_type: str = Field(min_length=1, max_length=127)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(min_length=1)
    rule_id: str = Field(pattern=SAFE_ID_PATTERN)
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED

    @field_validator("evidence_ids")
    @classmethod
    def valid_evidence_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            validate_safe_id(value, field_name="evidence_id")
        if len(values) != len(set(values)):
            raise ValueError("domain relation evidence IDs contain duplicates")
        return values


class DomainValidationFinding(DomainModel):
    code: str = Field(min_length=1, max_length=127)
    severity: Literal["info", "warning", "error"]
    message: str = Field(min_length=1, max_length=4000)
    element_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)

    @field_validator("element_ids", "relation_ids")
    @classmethod
    def safe_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            validate_safe_id(value)
        if len(values) != len(set(values)):
            raise ValueError("validation finding IDs contain duplicates")
        return values


class DomainMetrics(DomainModel):
    source_elements: int = Field(ge=0)
    source_relations: int = Field(ge=0)
    annotations: int = Field(ge=0)
    domain_relations: int = Field(ge=0)
    validation_findings: int = Field(ge=0)
    error_findings: int = Field(ge=0)
    annotation_evidence_coverage: float = Field(ge=0.0, le=1.0)
    fallback_used: bool = False


class DomainResult(DomainModel):
    domain_result_id: str = Field(pattern=SAFE_ID_PATTERN)
    domain_schema_version: str = DOMAIN_RESULT_SCHEMA_VERSION
    runtime_version: str = Field(min_length=1, max_length=63)
    runtime_digest: str = Field(pattern=SHA256_PATTERN)
    structure_id: str = Field(pattern=SAFE_ID_PATTERN)
    source_structure_digest: str = Field(pattern=SHA256_PATTERN)
    document_id: str = Field(pattern=SAFE_ID_PATTERN)
    parse_run_id: str = Field(pattern=SAFE_ID_PATTERN)
    pack_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    pack_version: str = Field(min_length=1, max_length=63)
    pack_digest: str = Field(pattern=SHA256_PATTERN)
    status: DomainExecutionStatus
    annotations: list[DomainAnnotation] = Field(default_factory=list)
    relations: list[DomainRelationAnnotation] = Field(default_factory=list)
    findings: list[DomainValidationFinding] = Field(default_factory=list)
    metrics: DomainMetrics
    failure_code: str | None = Field(default=None, max_length=127)
    failure_message: str | None = Field(default=None, max_length=4000)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("generated_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_result(self) -> DomainResult:
        annotation_ids = {item.annotation_id for item in self.annotations}
        if len(annotation_ids) != len(self.annotations):
            raise ValueError("duplicate domain annotation IDs")
        relation_ids = {item.relation_id for item in self.relations}
        if len(relation_ids) != len(self.relations):
            raise ValueError("duplicate domain relation IDs")
        element_ids = {item.element_id for item in self.annotations}
        for relation in self.relations:
            if relation.source_id not in element_ids or relation.target_id not in element_ids:
                raise ValueError("domain relation endpoints require domain annotations")
        if self.status == DomainExecutionStatus.FALLBACK_GENERIC:
            if self.annotations or self.relations:
                raise ValueError("fallback result cannot contain domain assertions")
            if not self.failure_code or not self.failure_message:
                raise ValueError("fallback result requires a failure code and message")
        elif self.failure_code is not None or self.failure_message is not None:
            raise ValueError("successful domain result cannot contain a failure")
        expected = {
            "annotations": len(self.annotations),
            "domain_relations": len(self.relations),
            "validation_findings": len(self.findings),
            "error_findings": sum(item.severity == "error" for item in self.findings),
            "fallback_used": self.status == DomainExecutionStatus.FALLBACK_GENERIC,
        }
        for field_name, value in expected.items():
            if getattr(self.metrics, field_name) != value:
                raise ValueError(f"domain metrics mismatch: {field_name}")
        if self.annotations and self.metrics.annotation_evidence_coverage != 1.0:
            raise ValueError("all domain annotations must retain evidence")
        return self

    def semantic_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("generated_at", None)
        return payload

    def semantic_digest(self) -> str:
        encoded = json.dumps(
            self.semantic_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
