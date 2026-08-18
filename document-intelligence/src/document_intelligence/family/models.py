from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.schema import SAFE_ID_PATTERN, SHA256_PATTERN, BaseType, validate_safe_id

FAMILY_DETECTION_SCHEMA_VERSION = "0.8"


class FamilyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class FamilyCueMatch(FamilyModel):
    cue_id: str = Field(pattern=SAFE_ID_PATTERN)
    weight: float = Field(gt=0.0, le=100.0)
    element_ids: list[str] = Field(min_length=1, max_length=256)
    evidence_ids: list[str] = Field(min_length=1, max_length=2048)

    @field_validator("element_ids", "evidence_ids")
    @classmethod
    def unique_safe_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            validate_safe_id(value)
        if len(values) != len(set(values)):
            raise ValueError("family cue matches cannot contain duplicate IDs")
        return values


class FamilyCandidate(FamilyModel):
    family_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    pack_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    pack_version: str = Field(min_length=1, max_length=63)
    pack_digest: str = Field(pattern=SHA256_PATTERN)
    profile_digest: str = Field(pattern=SHA256_PATTERN)
    priority: int = Field(ge=0, le=10000)
    eligible: bool
    score: float = Field(ge=0.0, le=1.0)
    positive_score: float = Field(ge=0.0)
    negative_score: float = Field(ge=0.0)
    positive_matches: list[FamilyCueMatch] = Field(default_factory=list)
    negative_matches: list[FamilyCueMatch] = Field(default_factory=list)
    missing_required_cues: list[str] = Field(default_factory=list)
    missing_base_types: dict[BaseType, int] = Field(default_factory=dict)
    exclusion_reasons: list[str] = Field(default_factory=list)

    @field_validator("missing_required_cues", "exclusion_reasons")
    @classmethod
    def unique_strings(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("candidate string lists cannot contain duplicates")
        return values


class FamilyDecision(StrEnum):
    CANDIDATE = "candidate"
    AMBIGUOUS = "ambiguous"
    NO_MATCH = "no_match"


class FamilyDetectionResult(FamilyModel):
    schema_version: Literal["0.8"] = FAMILY_DETECTION_SCHEMA_VERSION
    detection_id: str = Field(pattern=SAFE_ID_PATTERN)
    detector_version: str = Field(min_length=1, max_length=63)
    detector_digest: str = Field(pattern=SHA256_PATTERN)
    document_id: str = Field(pattern=SAFE_ID_PATTERN)
    parse_run_id: str = Field(pattern=SAFE_ID_PATTERN)
    source_document_digest: str = Field(pattern=SHA256_PATTERN)
    structure_id: str = Field(pattern=SAFE_ID_PATTERN)
    source_structure_digest: str = Field(pattern=SHA256_PATTERN)
    decision: FamilyDecision
    selected_family_id: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9-]{0,62}$"
    )
    selected_pack_id: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9-]{0,62}$"
    )
    selected_pack_version: str | None = Field(default=None, min_length=1, max_length=63)
    candidates: list[FamilyCandidate] = Field(default_factory=list, max_length=128)
    min_margin_observed: float | None = Field(default=None, ge=0.0, le=1.0)
    no_domain_action_executed: bool = True
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("generated_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_decision(self) -> FamilyDetectionResult:
        ranked = sorted(
            self.candidates,
            key=lambda item: (-int(item.eligible), -item.score, item.priority, item.family_id),
        )
        if self.candidates != ranked:
            raise ValueError("family candidates must use deterministic ranking order")
        selected = (
            self.selected_family_id,
            self.selected_pack_id,
            self.selected_pack_version,
        )
        if self.decision == FamilyDecision.CANDIDATE:
            if any(value is None for value in selected):
                raise ValueError("candidate decision requires a selected family and pack")
            if not self.candidates or not self.candidates[0].eligible:
                raise ValueError("candidate decision requires an eligible top candidate")
            top = self.candidates[0]
            if selected != (top.family_id, top.pack_id, top.pack_version):
                raise ValueError("selected family must equal the top ranked candidate")
        elif any(value is not None for value in selected):
            raise ValueError("non-candidate decisions cannot select a domain pack")
        if not self.no_domain_action_executed:
            raise ValueError("family detection is advisory and cannot execute domain actions")
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
