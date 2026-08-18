from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.schema import SAFE_ID_PATTERN, SHA256_PATTERN, BoundingBox


class MatchDecision(StrEnum):
    SAFE_STANDARD_REUSE = "safe_standard_reuse"
    AMBIGUOUS = "ambiguous"
    NO_MATCH = "no_match"


class MatchComponentScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    combined: float = Field(ge=0.0, le=1.0)
    local_feature: float = Field(ge=0.0, le=1.0)
    perceptual_hash: float = Field(ge=0.0, le=1.0)
    aspect_ratio: float = Field(ge=0.0, le=1.0)
    text: float = Field(ge=0.0, le=1.0)


class PageFingerprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standard_id: str = Field(pattern=SAFE_ID_PATTERN)
    fingerprint_version: str = Field(min_length=1, max_length=32)
    document_id: str = Field(pattern=SAFE_ID_PATTERN)
    page_id: str = Field(pattern=SAFE_ID_PATTERN)
    page_index: int = Field(ge=0)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    page_image_sha256: str = Field(pattern=SHA256_PATTERN)
    thumbnail_sha256: str = Field(pattern=SHA256_PATTERN)
    feature_sha256: str = Field(pattern=SHA256_PATTERN)
    perceptual_hash: str = Field(pattern=r"^[0-9a-f]{16}$")
    normalized_text: str
    text_ngram_hashes: list[str] = Field(default_factory=list)
    layout_digest: str = Field(pattern=SHA256_PATTERN)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    page_image_ref: str
    thumbnail_ref: str
    feature_ref: str
    keypoint_count: int = Field(ge=0)
    previous_page_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    next_page_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)

    @model_validator(mode="after")
    def refs_stay_in_standard(self) -> PageFingerprint:
        prefix = f"standard/documents/{self.standard_id}/"
        for field_name in ("page_image_ref", "thumbnail_ref", "feature_ref"):
            value = getattr(self, field_name)
            if not value.startswith(prefix) or ".." in value.split("/"):
                raise ValueError(f"{field_name} escapes its standard document namespace")
        return self


class StandardDocumentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standard_id: str = Field(pattern=SAFE_ID_PATTERN)
    fingerprint_version: str = Field(min_length=1, max_length=32)
    fingerprint_pipeline_digest: str = Field(pattern=SHA256_PATTERN)
    render_dpi: int = Field(gt=0, le=1200)
    document_id: str = Field(pattern=SAFE_ID_PATTERN)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    semantic_output_digest: str = Field(pattern=SHA256_PATTERN)
    schema_version: str
    source_ref: str
    document_ref: str
    document_sha256: str = Field(pattern=SHA256_PATTERN)
    reviewer: str = Field(min_length=1, max_length=127)
    approval_note: str = Field(min_length=1, max_length=2000)
    approved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    page_fingerprints: list[PageFingerprint]
    immutable: bool = True

    @field_validator("approved_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("approved_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def fingerprint_graph_consistent(self) -> StandardDocumentManifest:
        if not self.immutable:
            raise ValueError("standard document manifest must be immutable")
        if not self.page_fingerprints:
            raise ValueError("standard document requires at least one page fingerprint")
        page_ids = [item.page_id for item in self.page_fingerprints]
        page_indexes = [item.page_index for item in self.page_fingerprints]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("duplicate standard page_id")
        if sorted(page_indexes) != list(range(len(page_indexes))):
            raise ValueError("standard page indexes must be contiguous and start at zero")
        ordered = sorted(self.page_fingerprints, key=lambda item: item.page_index)
        for position, item in enumerate(ordered):
            if item.standard_id != self.standard_id:
                raise ValueError("page fingerprint standard_id mismatch")
            if item.document_id != self.document_id:
                raise ValueError("page fingerprint document_id mismatch")
            if item.source_sha256 != self.source_sha256:
                raise ValueError("page fingerprint source hash mismatch")
            if item.fingerprint_version != self.fingerprint_version:
                raise ValueError("page fingerprint version mismatch")
            expected_previous = ordered[position - 1].page_id if position else None
            expected_next = ordered[position + 1].page_id if position + 1 < len(ordered) else None
            if item.previous_page_id != expected_previous or item.next_page_id != expected_next:
                raise ValueError("page fingerprint neighbor chain is inconsistent")
        expected_document_ref = f"standard/documents/{self.standard_id}/document.json"
        if self.document_ref != expected_document_ref:
            raise ValueError("standard document_ref does not match standard_id")
        if not self.source_ref.startswith("sources/") or ".." in self.source_ref.split("/"):
            raise ValueError("standard source_ref is outside content-addressed sources")
        return self


class MatchEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_image_sha256: str = Field(pattern=SHA256_PATTERN)
    matched_region: BoundingBox | None = None
    homography: list[list[float]] | None = None
    local_matches: int = Field(ge=0)
    local_inliers: int = Field(ge=0)
    inlier_ratio: float = Field(ge=0.0, le=1.0)
    query_coverage: float = Field(ge=0.0, le=1.0)
    candidate_coverage: float = Field(ge=0.0, le=1.0)
    projected_area_ratio: float = Field(ge=0.0)
    transform_plausible: bool = False
    full_page_hash_gate: bool = False

    @field_validator("homography")
    @classmethod
    def homography_is_finite_3x3(
        cls, value: list[list[float]] | None
    ) -> list[list[float]] | None:
        if value is None:
            return None
        if len(value) != 3 or any(len(row) != 3 for row in value):
            raise ValueError("homography must be a 3x3 matrix")
        if any(not math.isfinite(number) for row in value for number in row):
            raise ValueError("homography must contain finite values")
        return value


class MatchCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standard_id: str = Field(pattern=SAFE_ID_PATTERN)
    document_id: str = Field(pattern=SAFE_ID_PATTERN)
    page_id: str = Field(pattern=SAFE_ID_PATTERN)
    page_index: int = Field(ge=0)
    scores: MatchComponentScores
    evidence: MatchEvidence
    standard_document_ref: str

    @model_validator(mode="after")
    def ref_matches_standard(self) -> MatchCandidate:
        expected = f"standard/documents/{self.standard_id}/document.json"
        if self.standard_document_ref != expected:
            raise ValueError("candidate standard_document_ref differs from standard_id")
        return self


class MatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: MatchDecision
    matcher_version: str = Field(min_length=1, max_length=32)
    matcher_digest: str = Field(pattern=SHA256_PATTERN)
    fingerprint_pipeline_digest: str = Field(pattern=SHA256_PATTERN)
    index_digest: str = Field(pattern=SHA256_PATTERN)
    query_page_index: int = Field(ge=0)
    threshold: float = Field(ge=0.0, le=1.0)
    local_threshold: float = Field(ge=0.0, le=1.0)
    min_margin: float = Field(ge=0.0, le=1.0)
    min_local_inliers: int = Field(ge=4)
    top1_score: float = Field(ge=0.0, le=1.0)
    top2_score: float = Field(ge=0.0, le=1.0)
    margin: float = Field(ge=0.0, le=1.0)
    candidates: list[MatchCandidate]
    safe_standard_ref: str | None = None
    reason: str

    @model_validator(mode="after")
    def decision_consistent(self) -> MatchResult:
        if self.candidates:
            candidate_scores = [item.scores.combined for item in self.candidates]
            if candidate_scores != sorted(candidate_scores, reverse=True):
                raise ValueError("match candidates must be sorted by descending score")
            candidate_keys = [
                (item.standard_id, item.page_id) for item in self.candidates
            ]
            if len(candidate_keys) != len(set(candidate_keys)):
                raise ValueError("match candidates contain duplicate standard pages")
            if abs(self.top1_score - self.candidates[0].scores.combined) > 1e-9:
                raise ValueError("top1_score differs from first candidate")
            expected_top2 = (
                self.candidates[1].scores.combined if len(self.candidates) > 1 else 0.0
            )
            if abs(self.top2_score - expected_top2) > 1e-9:
                raise ValueError("top2_score differs from second candidate")
        elif any((self.top1_score, self.top2_score, self.margin)):
            raise ValueError("empty candidate list requires zero scores and margin")
        expected_margin = max(0.0, self.top1_score - self.top2_score)
        if abs(self.margin - expected_margin) > 1e-9:
            raise ValueError("margin differs from top score difference")
        if self.decision == MatchDecision.SAFE_STANDARD_REUSE:
            if not self.candidates or not self.safe_standard_ref:
                raise ValueError("safe reuse requires a candidate and standard reference")
            best = self.candidates[0]
            if self.safe_standard_ref != best.standard_document_ref:
                raise ValueError("safe standard reference differs from top candidate")
            if self.margin < self.min_margin:
                raise ValueError("safe reuse requires the configured candidate margin")
            if best.evidence.full_page_hash_gate:
                if self.top1_score < self.threshold:
                    raise ValueError("safe full-page reuse is below the configured threshold")
            else:
                strong_local_gate = (
                    best.evidence.local_inliers >= self.min_local_inliers
                    and best.evidence.inlier_ratio >= 0.45
                    and best.evidence.query_coverage >= 0.08
                    and best.evidence.transform_plausible
                    and best.scores.local_feature >= 0.75
                )
                if self.top1_score < self.local_threshold or not strong_local_gate:
                    raise ValueError("safe local reuse does not satisfy local evidence gates")
        elif self.safe_standard_ref is not None:
            raise ValueError("non-safe decisions cannot expose a standard reference")
        return self
