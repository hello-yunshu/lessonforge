from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.schema import (
    SAFE_ID_PATTERN,
    SHA256_PATTERN,
    Evidence,
    Relation,
    ReviewStatus,
    validate_safe_id,
)

STRUCTURE_SCHEMA_VERSION = "1.0"


class StructureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class GroupKind(StrEnum):
    TEXT_CLUSTER = "text_cluster"
    VISUAL_WITH_CAPTION = "visual_with_caption"
    TABLE_WITH_CAPTION = "table_with_caption"
    REPEATED_MARGIN = "repeated_margin"


class DiagnosticSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class OutlineNode(StructureModel):
    node_id: str = Field(pattern=SAFE_ID_PATTERN)
    heading_element_id: str = Field(pattern=SAFE_ID_PATTERN)
    level: int = Field(ge=1, le=6)
    parent_node_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    page_index: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=2000)
    content_element_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(min_length=1)
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED

    @field_validator("content_element_ids", "evidence_ids")
    @classmethod
    def validate_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            validate_safe_id(value)
        if len(values) != len(set(values)):
            raise ValueError("identifier list contains duplicates")
        return values


class ContentGroup(StructureModel):
    group_id: str = Field(pattern=SAFE_ID_PATTERN)
    kind: GroupKind
    element_ids: list[str] = Field(min_length=1)
    page_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(min_length=1)
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED

    @field_validator("element_ids", "page_ids", "evidence_ids")
    @classmethod
    def validate_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            validate_safe_id(value)
        if len(values) != len(set(values)):
            raise ValueError("identifier list contains duplicates")
        return values


class StructureDiagnostic(StructureModel):
    code: str = Field(min_length=1, max_length=127)
    severity: DiagnosticSeverity
    message: str = Field(min_length=1, max_length=4000)
    page_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    element_ids: list[str] = Field(default_factory=list)

    @field_validator("element_ids")
    @classmethod
    def validate_element_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            validate_safe_id(value, field_name="element_id")
        if len(values) != len(set(values)):
            raise ValueError("diagnostic element_ids contains duplicates")
        return values


class StructureMetrics(StructureModel):
    total_elements: int = Field(ge=0)
    ordered_elements: int = Field(ge=0)
    content_elements: int = Field(ge=0)
    excluded_margin_elements: int = Field(ge=0)
    heading_elements: int = Field(ge=0)
    outline_nodes: int = Field(ge=0)
    groups: int = Field(ge=0)
    relations: int = Field(ge=0)
    cross_page_relations: int = Field(ge=0)
    reading_order_coverage: float = Field(ge=0.0, le=1.0)
    relation_evidence_coverage: float = Field(ge=0.0, le=1.0)
    consistency_score: float = Field(ge=0.0, le=1.0)


class StructureResult(StructureModel):
    structure_id: str = Field(pattern=SAFE_ID_PATTERN)
    structure_schema_version: str = STRUCTURE_SCHEMA_VERSION
    engine_version: str = Field(min_length=1, max_length=63)
    engine_digest: str = Field(pattern=SHA256_PATTERN)
    config_digest: str = Field(pattern=SHA256_PATTERN)
    document_id: str = Field(pattern=SAFE_ID_PATTERN)
    parse_run_id: str = Field(pattern=SAFE_ID_PATTERN)
    source_semantic_digest: str = Field(pattern=SHA256_PATTERN)
    reading_order: list[str]
    content_reading_order: list[str]
    excluded_margin_element_ids: list[str] = Field(default_factory=list)
    outline: list[OutlineNode] = Field(default_factory=list)
    groups: list[ContentGroup] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    diagnostics: list[StructureDiagnostic] = Field(default_factory=list)
    metrics: StructureMetrics
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator(
        "reading_order",
        "content_reading_order",
        "excluded_margin_element_ids",
    )
    @classmethod
    def validate_element_id_lists(cls, values: list[str]) -> list[str]:
        for value in values:
            validate_safe_id(value, field_name="element_id")
        if len(values) != len(set(values)):
            raise ValueError("element order list contains duplicates")
        return values

    @field_validator("generated_at")
    @classmethod
    def generated_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_graph(self) -> StructureResult:
        ordered = set(self.reading_order)
        content = set(self.content_reading_order)
        excluded = set(self.excluded_margin_element_ids)
        if not content.issubset(ordered):
            raise ValueError("content reading order must be a subset of reading order")
        if content & excluded:
            raise ValueError("excluded margin elements cannot appear in content order")
        if ordered != content | excluded:
            raise ValueError("reading order must equal content order plus excluded margins")

        evidence_ids = {item.evidence_id for item in self.evidence}
        if len(evidence_ids) != len(self.evidence):
            raise ValueError("duplicate structure evidence_id")
        relation_ids = {item.relation_id for item in self.relations}
        if len(relation_ids) != len(self.relations):
            raise ValueError("duplicate structure relation_id")
        group_ids = {item.group_id for item in self.groups}
        if len(group_ids) != len(self.groups):
            raise ValueError("duplicate structure group_id")
        node_ids = {item.node_id for item in self.outline}
        if len(node_ids) != len(self.outline):
            raise ValueError("duplicate outline node_id")

        for item in self.evidence:
            if item.parse_run_id != self.parse_run_id:
                raise ValueError("structure evidence parse_run_id mismatch")
        for relation in self.relations:
            if relation.source_id not in ordered or relation.target_id not in ordered:
                raise ValueError("structure relation references unordered element")
            if not set(relation.evidence_ids).issubset(evidence_ids):
                raise ValueError("structure relation references unknown evidence")
        for group in self.groups:
            if not set(group.element_ids).issubset(ordered):
                raise ValueError("structure group references unordered element")
            if not set(group.evidence_ids).issubset(evidence_ids):
                raise ValueError("structure group references unknown evidence")
        for node in self.outline:
            if node.heading_element_id not in content:
                raise ValueError("outline heading must appear in content reading order")
            if node.parent_node_id is not None and node.parent_node_id not in node_ids:
                raise ValueError("outline node references unknown parent")
            if node.parent_node_id == node.node_id:
                raise ValueError("outline node cannot parent itself")
            if not set(node.content_element_ids).issubset(content):
                raise ValueError("outline node references non-content element")
            if not set(node.evidence_ids).issubset(evidence_ids):
                raise ValueError("outline node references unknown evidence")
        self._validate_outline_cycles()

        if self.metrics.total_elements != len(self.reading_order):
            raise ValueError("metrics total_elements differs from reading_order")
        if self.metrics.ordered_elements != len(self.reading_order):
            raise ValueError("metrics ordered_elements differs from reading_order")
        if self.metrics.content_elements != len(self.content_reading_order):
            raise ValueError("metrics content_elements differs from content_reading_order")
        if self.metrics.excluded_margin_elements != len(excluded):
            raise ValueError("metrics excluded_margin_elements mismatch")
        if self.metrics.outline_nodes != len(self.outline):
            raise ValueError("metrics outline_nodes mismatch")
        if self.metrics.groups != len(self.groups):
            raise ValueError("metrics groups mismatch")
        if self.metrics.relations != len(self.relations):
            raise ValueError("metrics relations mismatch")
        return self

    def _validate_outline_cycles(self) -> None:
        parents = {item.node_id: item.parent_node_id for item in self.outline}
        for node_id in parents:
            seen: set[str] = set()
            current: str | None = node_id
            while current is not None:
                if current in seen:
                    raise ValueError("outline hierarchy contains a cycle")
                seen.add(current)
                current = parents.get(current)

    def semantic_dict(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("generated_at", None)
        for item in payload["evidence"]:
            item.pop("created_at", None)
            item.pop("raw_output_ref", None)
        return payload

    def semantic_digest(self) -> str:
        encoded = json.dumps(
            self.semantic_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
