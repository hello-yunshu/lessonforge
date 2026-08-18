from __future__ import annotations

import hashlib
import json
import math
from io import BytesIO
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from document_intelligence.exceptions import MatchInputError

from document_intelligence.matching.fingerprint import (
    dhash,
    dhash_similarity,
    extract_orb,
    text_jaccard,
    text_ngram_hashes,
)
from document_intelligence.matching.library import StandardLibrary
from document_intelligence.matching.models import (
    MatchCandidate,
    MatchComponentScores,
    MatchDecision,
    MatchEvidence,
    MatchResult,
    PageFingerprint,
)
from document_intelligence.schema import BoundingBox

MATCHER_VERSION = "1"


def _load_pymupdf() -> Any:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "PDF pixel rendering is disabled because the optional PyMuPDF renderer "
            "is not installed or qualified"
        ) from exc
    return fitz


class StandardMatcher:
    def __init__(
        self,
        library: StandardLibrary,
        *,
        high_threshold: float = 0.86,
        local_threshold: float = 0.78,
        min_margin: float = 0.08,
        min_local_inliers: int = 10,
        max_pdf_pages: int = 2000,
        max_render_pixels: int = 50_000_000,
        pdf_render_backend: str = "pymupdf",
    ) -> None:
        if not 0.0 <= high_threshold <= 1.0:
            raise ValueError("high_threshold must be between zero and one")
        if not 0.0 <= local_threshold <= 1.0:
            raise ValueError("local_threshold must be between zero and one")
        if not 0.0 <= min_margin <= 1.0:
            raise ValueError("min_margin must be between zero and one")
        if min_local_inliers < 4:
            raise ValueError("min_local_inliers must be at least four")
        if max_pdf_pages <= 0 or max_render_pixels <= 0:
            raise ValueError("resource limits must be positive")
        self.library = library
        self.high_threshold = high_threshold
        self.local_threshold = local_threshold
        self.min_margin = min_margin
        self.min_local_inliers = min_local_inliers
        self.max_pdf_pages = max_pdf_pages
        self.max_render_pixels = max_render_pixels
        self.pdf_render_backend = pdf_render_backend
        source = Path(__file__).read_bytes()
        self.matcher_digest = hashlib.sha256(
            source
            + b"\0"
            + MATCHER_VERSION.encode("ascii")
            + b"\0"
            + cv2.__version__.encode("utf-8")
        ).hexdigest()

    def match(
        self,
        content: bytes,
        mime_type: str,
        *,
        page_index: int = 0,
        query_text: str | None = None,
        top_k: int = 5,
    ) -> MatchResult:
        image = self._decode_query(content, mime_type, page_index=page_index)
        query_sha = self._query_sha(image)
        query_hash = dhash(image)
        query_points, query_descriptors = extract_orb(image)
        query_ngrams = text_ngram_hashes(query_text or "")
        fingerprints = self.library.load_page_index()
        index_payload = [item.model_dump(mode="json") for item in fingerprints]
        index_material = {
            "fingerprint_pipeline_digest": self.library.fingerprint_pipeline_digest,
            "pages": index_payload,
        }
        index_digest = hashlib.sha256(
            json.dumps(index_material, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        candidates = [
            self._score_candidate(
                image,
                query_sha,
                query_hash,
                query_points,
                query_descriptors,
                query_ngrams,
                fingerprint,
            )
            for fingerprint in fingerprints
        ]
        candidates.sort(key=lambda item: item.scores.combined, reverse=True)
        candidates = candidates[: max(1, top_k)]
        top1 = candidates[0].scores.combined if candidates else 0.0
        top2 = candidates[1].scores.combined if len(candidates) > 1 else 0.0
        margin = max(0.0, top1 - top2)
        if not candidates:
            return MatchResult(
                decision=MatchDecision.NO_MATCH,
                matcher_version=MATCHER_VERSION,
                matcher_digest=self.matcher_digest,
                fingerprint_pipeline_digest=self.library.fingerprint_pipeline_digest,
                index_digest=index_digest,
                query_page_index=page_index,
                threshold=self.high_threshold,
                local_threshold=self.local_threshold,
                min_margin=self.min_margin,
                min_local_inliers=self.min_local_inliers,
                top1_score=0.0,
                top2_score=0.0,
                margin=0.0,
                candidates=[],
                reason="standard library is empty",
            )
        best = candidates[0]
        strong_local_gate = (
            best.evidence.local_inliers >= self.min_local_inliers
            and best.evidence.inlier_ratio >= 0.45
            and best.evidence.query_coverage >= 0.08
            and best.evidence.transform_plausible
            and best.scores.local_feature >= 0.75
        )
        full_page_gate = best.evidence.full_page_hash_gate
        score_gate = (
            top1 >= self.high_threshold
            if full_page_gate
            else top1 >= self.local_threshold
        )
        if score_gate and margin >= self.min_margin and (full_page_gate or strong_local_gate):
            decision = MatchDecision.SAFE_STANDARD_REUSE
            safe_ref = best.standard_document_ref
            reason = "top candidate passed score, margin, and evidence gates"
        elif top1 >= self.high_threshold:
            decision = MatchDecision.AMBIGUOUS
            safe_ref = None
            reason = "high score without sufficient candidate separation or local evidence"
        else:
            decision = MatchDecision.NO_MATCH
            safe_ref = None
            reason = "top candidate did not reach the high-confidence threshold"
        return MatchResult(
            decision=decision,
            matcher_version=MATCHER_VERSION,
            matcher_digest=self.matcher_digest,
            fingerprint_pipeline_digest=self.library.fingerprint_pipeline_digest,
            index_digest=index_digest,
            query_page_index=page_index,
            threshold=self.high_threshold,
            local_threshold=self.local_threshold,
            min_margin=self.min_margin,
            min_local_inliers=self.min_local_inliers,
            top1_score=top1,
            top2_score=top2,
            margin=margin,
            candidates=candidates,
            safe_standard_ref=safe_ref,
            reason=reason,
        )

    def _score_candidate(
        self,
        query_image: np.ndarray,
        query_sha: str,
        query_hash: str,
        query_points: np.ndarray,
        query_descriptors: np.ndarray,
        query_ngrams: list[str],
        fingerprint: PageFingerprint,
    ) -> MatchCandidate:
        candidate_points, candidate_descriptors, candidate_width, candidate_height = (
            self.library.load_features(
                fingerprint.feature_ref, expected_sha256=fingerprint.feature_sha256
            )
        )
        (
            local_score,
            local_matches,
            inliers,
            inlier_ratio,
            query_coverage,
            candidate_coverage,
            projected_area_ratio,
            transform_plausible,
            homography,
            region,
        ) = self._local_score(
            query_image,
            query_points,
            query_descriptors,
            candidate_points,
            candidate_descriptors,
            candidate_width,
            candidate_height,
        )
        hash_score = dhash_similarity(query_hash, fingerprint.perceptual_hash)
        query_ratio = query_image.shape[1] / max(1, query_image.shape[0])
        candidate_ratio = fingerprint.width / fingerprint.height
        aspect_score = math.exp(-abs(math.log(max(query_ratio, 1e-9) / candidate_ratio)))
        text_score = text_jaccard(query_ngrams, fingerprint.text_ngram_hashes)
        exact_image_gate = query_sha == fingerprint.page_image_sha256
        full_geometry_gate = (
            inliers >= self.min_local_inliers
            and inlier_ratio >= 0.70
            and transform_plausible
            and 0.80 <= projected_area_ratio <= 1.20
        )
        full_page_hash_gate = (
            exact_image_gate
            or (aspect_score >= 0.98 and hash_score >= 0.984375 and full_geometry_gate)
        )
        if exact_image_gate:
            combined = 1.0
        elif local_matches >= 4:
            # Local crops naturally have weaker full-page hash/aspect signals. Once local
            # correspondences exist, the geometrically validated local score must dominate.
            combined = (
                0.87 * local_score
                + 0.07 * hash_score
                + 0.04 * aspect_score
                + 0.02 * text_score
            )
        else:
            combined = 0.72 * hash_score + 0.23 * aspect_score + 0.05 * text_score
        if local_matches < 4 and not full_page_hash_gate:
            combined *= 0.82
        combined = min(1.0, max(0.0, combined))
        return MatchCandidate(
            standard_id=fingerprint.standard_id,
            document_id=fingerprint.document_id,
            page_id=fingerprint.page_id,
            page_index=fingerprint.page_index,
            scores=MatchComponentScores(
                combined=combined,
                local_feature=local_score,
                perceptual_hash=hash_score,
                aspect_ratio=aspect_score,
                text=text_score,
            ),
            evidence=MatchEvidence(
                query_image_sha256=query_sha,
                matched_region=region,
                homography=homography,
                local_matches=local_matches,
                local_inliers=inliers,
                inlier_ratio=inlier_ratio,
                query_coverage=query_coverage,
                candidate_coverage=candidate_coverage,
                projected_area_ratio=projected_area_ratio,
                transform_plausible=transform_plausible,
                full_page_hash_gate=full_page_hash_gate,
            ),
            standard_document_ref=(
                f"standard/documents/{fingerprint.standard_id}/document.json"
            ),
        )

    @staticmethod
    def _local_score(
        query_image: np.ndarray,
        query_points: np.ndarray,
        query_descriptors: np.ndarray,
        candidate_points: np.ndarray,
        candidate_descriptors: np.ndarray,
        candidate_width: int,
        candidate_height: int,
    ) -> tuple[
        float,
        int,
        int,
        float,
        float,
        float,
        float,
        bool,
        list[list[float]] | None,
        BoundingBox | None,
    ]:
        empty = (0.0, 0, 0, 0.0, 0.0, 0.0, 0.0, False, None, None)
        if len(query_descriptors) < 4 or len(candidate_descriptors) < 4:
            return empty
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        pairs = matcher.knnMatch(query_descriptors, candidate_descriptors, k=2)
        good = [first for first, second in pairs if first.distance < 0.75 * second.distance]
        if len(good) < 4:
            return (0.0, len(good), 0, 0.0, 0.0, 0.0, 0.0, False, None, None)
        source = np.float32([query_points[item.queryIdx] for item in good]).reshape(-1, 1, 2)
        target = np.float32([candidate_points[item.trainIdx] for item in good]).reshape(-1, 1, 2)
        matrix, mask = cv2.findHomography(source, target, cv2.RANSAC, 4.0)
        if matrix is None or mask is None or not np.isfinite(matrix).all():
            return (0.0, len(good), 0, 0.0, 0.0, 0.0, 0.0, False, None, None)
        inlier_mask = mask.ravel().astype(bool)
        inliers = int(inlier_mask.sum())
        inlier_ratio = inliers / len(good)
        source_inliers = source.reshape(-1, 2)[inlier_mask]
        target_inliers = target.reshape(-1, 2)[inlier_mask]

        def hull_coverage(points: np.ndarray, area: float) -> float:
            if len(points) < 3 or area <= 0:
                return 0.0
            hull = cv2.convexHull(points.astype(np.float32))
            return min(1.0, max(0.0, cv2.contourArea(hull) / area))

        query_area = float(query_image.shape[0] * query_image.shape[1])
        candidate_area = float(candidate_width * candidate_height)
        query_coverage = hull_coverage(source_inliers, query_area)
        candidate_coverage = hull_coverage(target_inliers, candidate_area)
        height, width = query_image.shape[:2]
        corners = np.float32(
            [[[0, 0]], [[width - 1, 0]], [[width - 1, height - 1]], [[0, height - 1]]]
        )
        transformed = cv2.perspectiveTransform(corners, matrix).reshape(-1, 2)
        projected_area_ratio = (
            abs(cv2.contourArea(transformed.astype(np.float32))) / candidate_area
            if np.isfinite(transformed).all() and candidate_area > 0
            else 0.0
        )
        transform_plausible = bool(
            np.isfinite(transformed).all()
            and 0.005 <= projected_area_ratio <= 1.5
            and cv2.isContourConvex(transformed.astype(np.float32))
        )
        count_score = min(1.0, inliers / 30.0)
        coverage_score = min(1.0, query_coverage / 0.18)
        geometry_score = 1.0 if transform_plausible else 0.0
        local_score = (
            0.30 * count_score
            + 0.35 * min(1.0, inlier_ratio)
            + 0.25 * coverage_score
            + 0.10 * geometry_score
        )
        x1 = float(np.clip(transformed[:, 0].min() / candidate_width, 0.0, 1.0))
        y1 = float(np.clip(transformed[:, 1].min() / candidate_height, 0.0, 1.0))
        x2 = float(np.clip(transformed[:, 0].max() / candidate_width, 0.0, 1.0))
        y2 = float(np.clip(transformed[:, 1].max() / candidate_height, 0.0, 1.0))
        region = BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2) if x2 >= x1 and y2 >= y1 else None
        return (
            min(1.0, local_score),
            len(good),
            inliers,
            min(1.0, inlier_ratio),
            query_coverage,
            candidate_coverage,
            projected_area_ratio,
            transform_plausible,
            [[float(value) for value in row] for row in matrix.tolist()],
            region,
        )

    def _decode_query(self, content: bytes, mime_type: str, *, page_index: int) -> np.ndarray:
        if mime_type == "application/pdf":
            if self.pdf_render_backend != "pymupdf":
                raise MatchInputError(
                    "PDF matching is disabled by deployment policy"
                )
            try:
                fitz = _load_pymupdf()
                document = fitz.open(stream=content, filetype="pdf")
            except Exception as exc:
                raise MatchInputError(f"unable to open query PDF: {exc}") from exc
            try:
                if document.needs_pass:
                    raise MatchInputError("encrypted PDF is not accepted for matching")
                if document.page_count <= 0 or document.page_count > self.max_pdf_pages:
                    raise MatchInputError(
                        f"PDF page count outside limits: {document.page_count}"
                    )
                if page_index < 0 or page_index >= document.page_count:
                    raise MatchInputError("page_index is outside the PDF")
                page = document[page_index]
                scale = 2.0
                width = max(1, round(page.rect.width * scale))
                height = max(1, round(page.rect.height * scale))
                if width * height > self.max_render_pixels:
                    raise MatchInputError(
                        f"rendered query page exceeds pixel limit: {width * height} > "
                        f"{self.max_render_pixels}"
                    )
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                array = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                    pixmap.height, pixmap.width, pixmap.n
                )
                return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
            finally:
                document.close()
        if mime_type.startswith("image/"):
            try:
                with Image.open(BytesIO(content)) as image:
                    width, height = image.size
                    if width * height > self.max_render_pixels:
                        raise MatchInputError(
                            f"query image exceeds pixel limit: {width * height} > "
                            f"{self.max_render_pixels}"
                        )
                    rgb = np.array(image.convert("RGB"))
            except MatchInputError:
                raise
            except Exception as exc:
                raise MatchInputError(f"unable to decode query image: {exc}") from exc
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        raise MatchInputError(f"unsupported query MIME: {mime_type}")

    @staticmethod
    def _query_sha(image: np.ndarray) -> str:
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            raise ValueError("unable to encode query image")
        return hashlib.sha256(encoded.tobytes()).hexdigest()
