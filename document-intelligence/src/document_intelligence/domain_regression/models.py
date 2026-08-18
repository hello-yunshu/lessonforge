from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.schema import BaseType, BoundingBox


class RegressionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RegressionElementSpec(RegressionModel):
    element_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    base_type: BaseType
    subtype: str = Field(default="fixture", min_length=1, max_length=127)
    text: str | None = Field(default=None, max_length=10000)
    bbox: BoundingBox


class DomainRegressionCase(RegressionModel):
    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(default="application/pdf", min_length=1, max_length=127)
    expected_pack_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    expected_family_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    expected_annotation_types: list[str] = Field(min_length=1, max_length=128)
    forbidden_annotation_types: list[str] = Field(default_factory=list, max_length=128)
    maximum_error_findings: int = Field(default=0, ge=0, le=10000)
    elements: list[RegressionElementSpec] = Field(min_length=1, max_length=10000)

    @field_validator("expected_annotation_types", "forbidden_annotation_types")
    @classmethod
    def unique_types(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("regression annotation type lists cannot contain duplicates")
        return values

    @model_validator(mode="after")
    def disjoint_types(self) -> DomainRegressionCase:
        if set(self.expected_annotation_types) & set(self.forbidden_annotation_types):
            raise ValueError("expected and forbidden annotation types must be disjoint")
        element_ids = [item.element_id for item in self.elements]
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("regression element IDs must be unique within a case")
        return self


class CrossDomainRegressionSuite(RegressionModel):
    version: Literal[1] = 1
    core_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: list[DomainRegressionCase] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def unique_cases(self) -> CrossDomainRegressionSuite:
        ids = [item.case_id for item in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("cross-domain regression case IDs must be unique")
        return self


class DomainRegressionCaseResult(RegressionModel):
    case_id: str
    passed: bool
    expected_pack_id: str
    detected_pack_id: str | None = None
    detected_family_id: str | None = None
    annotation_types: list[str] = Field(default_factory=list)
    error_findings: int = Field(ge=0)
    family_score: float = Field(ge=0.0, le=1.0)
    source_unchanged: bool
    evidence_complete: bool
    isolated_results: bool
    failure_codes: list[str] = Field(default_factory=list)


class CrossDomainRegressionReport(RegressionModel):
    schema_version: Literal["0.8"] = "0.8"
    suite_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    engine_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    detector_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    passed: bool
    total_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    family_accuracy: float = Field(ge=0.0, le=1.0)
    core_schema_unchanged: bool
    bounded_auto: bool = False
    cases: list[DomainRegressionCaseResult]

    @model_validator(mode="after")
    def consistent_counts(self) -> CrossDomainRegressionReport:
        if self.total_cases != len(self.cases):
            raise ValueError("cross-domain report total_cases mismatch")
        if self.passed_cases != sum(item.passed for item in self.cases):
            raise ValueError("cross-domain report passed_cases mismatch")
        if self.passed != (self.passed_cases == self.total_cases and self.core_schema_unchanged):
            raise ValueError("cross-domain report pass status mismatch")
        if self.bounded_auto:
            raise ValueError("cross-domain regression cannot enable boundedAuto")
        return self

    def semantic_digest(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
