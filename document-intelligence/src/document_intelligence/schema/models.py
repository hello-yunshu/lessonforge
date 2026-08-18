from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import PurePath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

SCHEMA_VERSION = "1.1"
SAFE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
_SAFE_ID_RE = re.compile(SAFE_ID_PATTERN)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    REJECTED = "rejected"


class BaseType(StrEnum):
    TEXT = "text"
    HEADING = "heading"
    IMAGE = "image"
    FIGURE = "figure"
    FORMULA = "formula"
    TABLE = "table"
    ICON = "icon"
    CHARACTER = "character"
    CALLOUT = "callout"
    LIST = "list"
    FOOTNOTE = "footnote"
    PAGE_NUMBER = "page_number"
    INPUT_AREA = "input_area"
    SEPARATOR = "separator"
    UNKNOWN = "unknown"


class EvidenceKind(StrEnum):
    NATIVE_EXTRACTION = "native_extraction"
    MODEL_PREDICTION = "model_prediction"
    RULE_INFERENCE = "rule_inference"
    HUMAN_REVIEW = "human_review"
    EXTERNAL_REFERENCE = "external_reference"


def validate_safe_id(value: str, *, field_name: str = "id") -> str:
    if not _SAFE_ID_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} must match {SAFE_ID_PATTERN!r}; "
            "path separators and traversal are forbidden"
        )
    return value


class BoundingBox(StrictModel):
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def valid_order(self) -> BoundingBox:
        if self.x2 < self.x1 or self.y2 < self.y1:
            raise ValueError("bbox coordinates must satisfy x1<=x2 and y1<=y2")
        return self


class PixelBoundingBox(StrictModel):
    x1: float = Field(ge=0.0)
    y1: float = Field(ge=0.0)
    x2: float = Field(ge=0.0)
    y2: float = Field(ge=0.0)

    @model_validator(mode="after")
    def valid_order(self) -> PixelBoundingBox:
        if self.x2 < self.x1 or self.y2 < self.y1:
            raise ValueError("pixel bbox coordinates must satisfy x1<=x2 and y1<=y2")
        return self


class SourceDescriptor(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=SHA256_PATTERN)
    mime_type: str = Field(min_length=1, max_length=127)
    size_bytes: int = Field(ge=0)
    source_ref: str | None = None

    @field_validator("filename")
    @classmethod
    def filename_is_basename(cls, value: str) -> str:
        if PurePath(value).name != value or any(ord(char) < 32 for char in value):
            raise ValueError("filename must be a control-character-free basename")
        return value


class DocumentIdentity(StrictModel):
    family: str | None = None
    edition: str | None = None
    external_id: str | None = None


class Confidence(StrictModel):
    overall: float = Field(ge=0.0, le=1.0)
    detection: float | None = Field(default=None, ge=0.0, le=1.0)
    recognition: float | None = Field(default=None, ge=0.0, le=1.0)


class ElementContent(StrictModel):
    text: str | None = None
    latex: str | None = None
    table: list[list[str]] | None = None
    asset_ref: str | None = None


class Page(StrictModel):
    page_id: str = Field(pattern=SAFE_ID_PATTERN)
    index: int = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    rotation: int = 0
    element_ids: list[str] = Field(default_factory=list)
    image_ref: str | None = None

    @field_validator("rotation")
    @classmethod
    def valid_rotation(cls, value: int) -> int:
        normalized = value % 360
        if normalized not in {0, 90, 180, 270}:
            raise ValueError("rotation must be 0, 90, 180, or 270 degrees")
        return normalized

    @field_validator("element_ids")
    @classmethod
    def valid_element_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            validate_safe_id(value, field_name="element_id")
        if len(values) != len(set(values)):
            raise ValueError("page.element_ids contains duplicates")
        return values


class Element(StrictModel):
    element_id: str = Field(pattern=SAFE_ID_PATTERN)
    page_id: str = Field(pattern=SAFE_ID_PATTERN)
    base_type: BaseType
    subtype: str = Field(min_length=1, max_length=127)
    bbox: BoundingBox
    pixel_bbox: PixelBoundingBox | None = None
    content: ElementContent
    confidence: Confidence
    evidence_ids: list[str] = Field(min_length=1)
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    domain_annotations: list[dict[str, JsonValue]] = Field(default_factory=list)
    reading_order: int | None = Field(default=None, ge=0)

    @field_validator("evidence_ids")
    @classmethod
    def valid_evidence_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            validate_safe_id(value, field_name="evidence_id")
        if len(values) != len(set(values)):
            raise ValueError("element.evidence_ids contains duplicates")
        return values


class Relation(StrictModel):
    relation_id: str = Field(pattern=SAFE_ID_PATTERN)
    source_id: str = Field(pattern=SAFE_ID_PATTERN)
    target_id: str = Field(pattern=SAFE_ID_PATTERN)
    type: str = Field(min_length=1, max_length=127)
    domain_type: str | None = Field(default=None, min_length=1, max_length=127)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(min_length=1)
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED

    @field_validator("evidence_ids")
    @classmethod
    def valid_evidence_ids(cls, values: list[str]) -> list[str]:
        for value in values:
            validate_safe_id(value, field_name="evidence_id")
        if len(values) != len(set(values)):
            raise ValueError("relation.evidence_ids contains duplicates")
        return values


class Evidence(StrictModel):
    evidence_id: str = Field(pattern=SAFE_ID_PATTERN)
    kind: EvidenceKind
    producer: str = Field(min_length=1, max_length=127)
    producer_version: str = Field(min_length=1, max_length=127)
    model_digest: str = Field(pattern=SHA256_PATTERN)
    parse_run_id: str = Field(pattern=SAFE_ID_PATTERN)
    source_page_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    bbox: BoundingBox | None = None
    raw_output_ref: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class ResourceUsage(StrictModel):
    duration_ms: float = Field(ge=0.0)
    max_rss_kb: int | None = Field(default=None, ge=0)
    input_bytes: int = Field(ge=0)
    output_elements: int = Field(ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)


class ParseWarning(StrictModel):
    code: str = Field(min_length=1, max_length=127)
    message: str = Field(min_length=1)
    severity: str = Field(default="P2", pattern=r"^P[0-2]$")
    page_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)


class ParseErrorRecord(StrictModel):
    code: str = Field(min_length=1, max_length=127)
    message: str = Field(min_length=1)
    severity: str = Field(pattern=r"^P[0-2]$")
    parser_id: str = Field(min_length=1, max_length=127)
    retryable: bool = False


class ParseRun(StrictModel):
    parse_run_id: str = Field(pattern=SAFE_ID_PATTERN)
    input_sha256: str = Field(pattern=SHA256_PATTERN)
    parser_id: str = Field(min_length=1, max_length=127)
    parser_version: str = Field(min_length=1, max_length=127)
    parser_digest: str = Field(pattern=SHA256_PATTERN)
    config_digest: str = Field(pattern=SHA256_PATTERN)
    request_context_digest: str = Field(pattern=SHA256_PATTERN)
    domain_pack: str | None = None
    rule_pack: str | None = None
    rill_decision_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    semantic_output_digest: str | None = Field(default=None, pattern=SHA256_PATTERN)
    resource_usage: ResourceUsage | None = None
    warnings: list[ParseWarning] = Field(default_factory=list)
    errors: list[ParseErrorRecord] = Field(default_factory=list)

    @field_validator("started_at", "finished_at")
    @classmethod
    def timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("run timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def valid_lifecycle(self) -> ParseRun:
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at cannot precede started_at")
        if self.status in {RunStatus.SUCCEEDED, RunStatus.FAILED} and self.finished_at is None:
            raise ValueError("terminal run status requires finished_at")
        if self.status == RunStatus.SUCCEEDED:
            if self.semantic_output_digest is None or self.resource_usage is None:
                raise ValueError(
                    "successful run requires semantic_output_digest and resource_usage"
                )
        return self


class ParsedDocument(StrictModel):
    document_id: str = Field(pattern=SAFE_ID_PATTERN)
    schema_version: str = SCHEMA_VERSION
    source: SourceDescriptor
    identity: DocumentIdentity = Field(default_factory=DocumentIdentity)
    pages: list[Page]
    elements: list[Element]
    relations: list[Relation] = Field(default_factory=list)
    evidence: list[Evidence]
    domain_pack: str | None = None
    status: str = Field(default="parsed", min_length=1, max_length=63)
    parse_run_id: str = Field(pattern=SAFE_ID_PATTERN)

    @model_validator(mode="after")
    def validate_graph(self) -> ParsedDocument:
        page_ids = {page.page_id for page in self.pages}
        element_ids = {element.element_id for element in self.elements}
        evidence_ids = {item.evidence_id for item in self.evidence}
        relation_ids = {item.relation_id for item in self.relations}
        if len(page_ids) != len(self.pages):
            raise ValueError("duplicate page_id")
        if len(element_ids) != len(self.elements):
            raise ValueError("duplicate element_id")
        if len(evidence_ids) != len(self.evidence):
            raise ValueError("duplicate evidence_id")
        if len(relation_ids) != len(self.relations):
            raise ValueError("duplicate relation_id")
        page_indexes = [page.index for page in self.pages]
        if len(page_indexes) != len(set(page_indexes)):
            raise ValueError("duplicate page index")
        if sorted(page_indexes) != list(range(len(page_indexes))):
            raise ValueError("page indexes must be contiguous and start at zero")

        expected_by_page: dict[str, set[str]] = {page_id: set() for page_id in page_ids}
        for element in self.elements:
            if element.page_id not in page_ids:
                raise ValueError(f"element references unknown page: {element.page_id}")
            expected_by_page[element.page_id].add(element.element_id)
            missing = set(element.evidence_ids) - evidence_ids
            if missing:
                raise ValueError(f"element references unknown evidence: {sorted(missing)}")
        for page in self.pages:
            actual = set(page.element_ids)
            expected = expected_by_page[page.page_id]
            if actual != expected:
                raise ValueError(
                    f"page element membership mismatch for {page.page_id}: "
                    f"missing={sorted(expected - actual)}, foreign={sorted(actual - expected)}"
                )
        for relation in self.relations:
            if relation.source_id not in element_ids or relation.target_id not in element_ids:
                raise ValueError("relation references unknown element")
            missing = set(relation.evidence_ids) - evidence_ids
            if missing:
                raise ValueError(f"relation references unknown evidence: {sorted(missing)}")
        for item in self.evidence:
            if item.parse_run_id != self.parse_run_id:
                raise ValueError("evidence parse_run_id differs from document parse_run_id")
            if item.source_page_id is not None and item.source_page_id not in page_ids:
                raise ValueError("evidence references unknown source page")
            if item.bbox is not None and item.source_page_id is None:
                raise ValueError("evidence bbox requires source_page_id")
        return self

    def semantic_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["source"].pop("source_ref", None)
        for item in data["evidence"]:
            item.pop("created_at", None)
            item.pop("raw_output_ref", None)
        return data

    def semantic_digest(self) -> str:
        payload = json.dumps(
            self.semantic_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class ParseRequest(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=127)
    content: bytes = Field(repr=False)
    parser_id: str | None = None
    domain_pack: str | None = None
    options: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("filename")
    @classmethod
    def safe_filename(cls, value: str) -> str:
        if PurePath(value).name != value or any(ord(char) < 32 for char in value):
            raise ValueError("filename must be a control-character-free basename")
        return value

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    def context_digest(self) -> str:
        payload = {
            "filename": self.filename,
            "mime_type": self.mime_type,
            "domain_pack": self.domain_pack,
            "options": self.options,
        }
        material = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()


class ParserHealth(StrictModel):
    parser_id: str = Field(min_length=1, max_length=127)
    available: bool
    enabled: bool
    version: str = Field(min_length=1, max_length=127)
    artifact_digest: str | None = Field(default=None, pattern=SHA256_PATTERN)
    reason: str | None = None
    capabilities: list[str] = Field(default_factory=list)


class ParserResult(StrictModel):
    document: ParsedDocument
    run: ParseRun
    raw_output: dict[str, JsonValue] | list[JsonValue] | str | None = None
    binary_artifacts: dict[str, bytes] = Field(default_factory=dict, exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_run_links(self) -> ParserResult:
        if self.document.parse_run_id != self.run.parse_run_id:
            raise ValueError("document and run IDs differ")
        if self.document.source.sha256 != self.run.input_sha256:
            raise ValueError("document source and run input hashes differ")
        return self
