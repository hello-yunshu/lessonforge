from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.schema import (
    SAFE_ID_PATTERN,
    SHA256_PATTERN,
    BoundingBox,
    validate_safe_id,
)


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class LabelUObject(ReviewModel):
    id: str = Field(pattern=SAFE_ID_PATTERN)
    element_id: str = Field(pattern=SAFE_ID_PATTERN)
    label: str = Field(min_length=1, max_length=127)
    bbox: BoundingBox
    text: str | None = Field(default=None, max_length=10000)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(min_length=1)


class LabelURelation(ReviewModel):
    id: str = Field(pattern=SAFE_ID_PATTERN)
    source_id: str = Field(pattern=SAFE_ID_PATTERN)
    target_id: str = Field(pattern=SAFE_ID_PATTERN)
    label: str = Field(min_length=1, max_length=127)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(min_length=1)


class LabelUTask(ReviewModel):
    task_id: str = Field(pattern=SAFE_ID_PATTERN)
    page_id: str = Field(pattern=SAFE_ID_PATTERN)
    image_ref: str | None = None
    objects: list[LabelUObject] = Field(default_factory=list)
    relations: list[LabelURelation] = Field(default_factory=list)


class LabelUReviewExport(ReviewModel):
    adapter: Literal["labelu-json-v1"] = "labelu-json-v1"
    export_id: str = Field(pattern=SAFE_ID_PATTERN)
    domain_result_id: str = Field(pattern=SAFE_ID_PATTERN)
    source_domain_digest: str = Field(pattern=SHA256_PATTERN)
    pack_id: str
    pack_version: str
    object_labels: list[str] = Field(default_factory=list)
    relation_labels: list[str] = Field(default_factory=list)
    tasks: list[LabelUTask]
    cross_page_relations: list[LabelURelation] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    def semantic_digest(self) -> str:
        payload = self.model_dump(mode="json")
        payload.pop("created_at", None)
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()


class ReviewedObject(ReviewModel):
    element_id: str = Field(pattern=SAFE_ID_PATTERN)
    labels: list[str] = Field(default_factory=list)

    @field_validator("labels")
    @classmethod
    def unique_labels(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("review labels contain duplicates")
        return values


class ReviewedRelation(ReviewModel):
    source_id: str = Field(pattern=SAFE_ID_PATTERN)
    target_id: str = Field(pattern=SAFE_ID_PATTERN)
    label: str = Field(min_length=1, max_length=127)


class LabelUReviewSubmission(ReviewModel):
    adapter: Literal["labelu-json-v1"] = "labelu-json-v1"
    export_id: str = Field(pattern=SAFE_ID_PATTERN)
    domain_result_id: str = Field(pattern=SAFE_ID_PATTERN)
    source_domain_digest: str = Field(pattern=SHA256_PATTERN)
    reviewer: str = Field(min_length=1, max_length=127)
    review_level: Literal["reviewer", "domain-expert"]
    reason: str = Field(min_length=1, max_length=4000)
    objects: list[ReviewedObject] = Field(default_factory=list)
    relations: list[ReviewedRelation] = Field(default_factory=list)
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("submitted_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("submitted_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def unique_review_items(self) -> LabelUReviewSubmission:
        element_ids = [item.element_id for item in self.objects]
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("review submission has duplicate element IDs")
        relation_keys = [(item.source_id, item.target_id, item.label) for item in self.relations]
        if len(relation_keys) != len(set(relation_keys)):
            raise ValueError("review submission has duplicate relations")
        return self


class ReviewRecord(ReviewModel):
    review_id: str = Field(pattern=SAFE_ID_PATTERN)
    export_id: str = Field(pattern=SAFE_ID_PATTERN)
    domain_result_id: str = Field(pattern=SAFE_ID_PATTERN)
    source_domain_digest: str = Field(pattern=SHA256_PATTERN)
    reviewer: str
    review_level: Literal["reviewer", "domain-expert"]
    reason: str
    objects: list[ReviewedObject]
    relations: list[ReviewedRelation]
    submitted_at: datetime

    def semantic_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.model_dump(mode="json"),
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
