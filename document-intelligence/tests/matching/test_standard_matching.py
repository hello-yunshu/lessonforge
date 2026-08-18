from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from document_intelligence.exceptions import (
    MatchInputError,
    StandardApprovalError,
    StandardStoreCorruptError,
)
from document_intelligence.matching import MatchDecision, StandardLibrary, StandardMatcher
from document_intelligence.parser_sdk import ParserRegistry
from document_intelligence.parsers import NativePdfParser
from document_intelligence.schema import ParseRequest
from document_intelligence.services import ArtifactStore, ParseOrchestrator


def _parse_and_register(path: Path, store: ArtifactStore, *, filename: str | None = None):
    orchestrator = ParseOrchestrator(ParserRegistry([NativePdfParser()]), store)
    request = ParseRequest(
        filename=filename or path.name,
        mime_type="application/pdf",
        content=path.read_bytes(),
        parser_id="native-pdf",
    )
    result = orchestrator.parse(request)
    library = StandardLibrary(store)
    manifest = library.register_run(
        result.run.parse_run_id,
        reviewer="fixture-reviewer",
        approval_note="verified synthetic fixture",
        approved=True,
    )
    return library, manifest


def _encode(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def test_standard_registration_requires_explicit_approval(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    orchestrator = ParseOrchestrator(ParserRegistry([NativePdfParser()]), store)
    path = fixtures_dir / "native_text.pdf"
    result = orchestrator.parse(
        ParseRequest(filename=path.name, mime_type="application/pdf", content=path.read_bytes())
    )
    with pytest.raises(StandardApprovalError):
        StandardLibrary(store).register_run(
            result.run.parse_run_id,
            reviewer="reviewer",
            approval_note="not approved",
            approved=False,
        )


def test_full_page_and_crop_match_safe_standard(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library, manifest = _parse_and_register(fixtures_dir / "native_text.pdf", store)
    matcher = StandardMatcher(library)
    fingerprint = manifest.page_fingerprints[0]
    image = library.read_image(fingerprint.page_image_ref)

    full = matcher.match(_encode(image), "image/png")
    assert full.decision == MatchDecision.SAFE_STANDARD_REUSE
    assert full.candidates[0].page_id == fingerprint.page_id
    assert full.safe_standard_ref

    height, width = image.shape[:2]
    crop = image[int(height * 0.15) : int(height * 0.75), int(width * 0.1) : int(width * 0.9)]
    cropped = matcher.match(_encode(crop), "image/png")
    assert cropped.decision == MatchDecision.SAFE_STANDARD_REUSE
    assert cropped.candidates[0].page_id == fingerprint.page_id
    assert cropped.candidates[0].evidence.local_inliers >= 10
    assert cropped.candidates[0].evidence.query_coverage >= 0.08
    assert cropped.candidates[0].evidence.matched_region is not None


def test_unknown_image_is_not_forced_to_standard(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library, _ = _parse_and_register(fixtures_dir / "native_text.pdf", store)
    matcher = StandardMatcher(library)
    unknown = np.full((1200, 800, 3), 255, dtype=np.uint8)
    cv2.putText(
        unknown,
        "Completely unknown 93741",
        (40, 300),
        cv2.FONT_HERSHEY_SIMPLEX,
        2,
        (0, 0, 0),
        4,
    )
    result = matcher.match(_encode(unknown), "image/png")
    assert result.decision == MatchDecision.NO_MATCH
    assert result.safe_standard_ref is None


def test_duplicate_standard_pages_are_ambiguous(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library, first = _parse_and_register(
        fixtures_dir / "native_text.pdf", store, filename="first.pdf"
    )
    _, second = _parse_and_register(
        fixtures_dir / "native_text.pdf", store, filename="second.pdf"
    )
    assert first.standard_id != second.standard_id
    image = library.read_image(first.page_fingerprints[0].page_image_ref)
    result = StandardMatcher(library).match(_encode(image), "image/png")
    assert result.decision == MatchDecision.AMBIGUOUS
    assert result.margin < result.min_margin
    assert result.safe_standard_ref is None


def test_standard_document_is_immutable_and_rebuildable(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library, manifest = _parse_and_register(fixtures_dir / "native_text.pdf", store)
    again = library.register_run(
        store.read_result(
            next(path.name for path in store.runs_dir.iterdir() if path.is_dir())
        ).run.parse_run_id,
        reviewer="other",
        approval_note="should return immutable existing version",
        approved=True,
    )
    assert again == manifest
    library.index_path.unlink()
    library._atomic_json(library.index_path, {"version": 1, "pages": []})
    library.rebuild_index()
    assert len(library.load_page_index()) == 1


def test_safe_reuse_also_requires_total_score_threshold(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library, manifest = _parse_and_register(fixtures_dir / "native_text.pdf", store)
    fingerprint = manifest.page_fingerprints[0]
    image = library.read_image(fingerprint.page_image_ref)
    height, width = image.shape[:2]
    crop = image[int(height * 0.15) : int(height * 0.75), int(width * 0.1) : int(width * 0.9)]
    result = StandardMatcher(
        library, high_threshold=0.999999, local_threshold=0.999999
    ).match(
        _encode(crop), "image/png"
    )
    assert result.candidates[0].evidence.local_inliers >= 10
    assert result.top1_score < result.threshold
    assert result.decision != MatchDecision.SAFE_STANDARD_REUSE
    assert result.safe_standard_ref is None


def test_standard_registration_enforces_render_pixel_limit(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    orchestrator = ParseOrchestrator(ParserRegistry([NativePdfParser()]), store)
    path = fixtures_dir / "native_text.pdf"
    result = orchestrator.parse(
        ParseRequest(filename=path.name, mime_type="application/pdf", content=path.read_bytes())
    )
    with pytest.raises(StandardApprovalError, match="pixel limit"):
        StandardLibrary(store, max_render_pixels=100).register_run(
            result.run.parse_run_id,
            reviewer="reviewer",
            approval_note="limit regression",
            approved=True,
        )


def test_matcher_enforces_pdf_render_pixel_limit(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library, _ = _parse_and_register(fixtures_dir / "native_text.pdf", store)
    content = (fixtures_dir / "native_text.pdf").read_bytes()
    with pytest.raises(MatchInputError, match="pixel limit"):
        StandardMatcher(library, max_render_pixels=100).match(
            content, "application/pdf"
        )


def test_standard_manifest_binds_fingerprint_pipeline(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library, manifest = _parse_and_register(fixtures_dir / "native_text.pdf", store)
    assert manifest.fingerprint_version == "2"
    assert manifest.fingerprint_pipeline_digest == library.fingerprint_pipeline_digest
    assert manifest.render_dpi == library.render_dpi
    assert all(
        item.fingerprint_version == manifest.fingerprint_version
        for item in manifest.page_fingerprints
    )


def test_match_result_records_reproducibility_metadata(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library, manifest = _parse_and_register(fixtures_dir / "native_text.pdf", store)
    image = library.read_image(manifest.page_fingerprints[0].page_image_ref)
    result = StandardMatcher(library).match(_encode(image), "image/png")
    assert result.matcher_version == "1"
    assert len(result.matcher_digest) == 64
    assert len(result.index_digest) == 64
    assert result.fingerprint_pipeline_digest == library.fingerprint_pipeline_digest
    assert result.query_page_index == 0
    assert result.local_threshold == 0.78
    assert result.min_local_inliers == 10


def test_corrupt_standard_index_fails_closed(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library, _ = _parse_and_register(fixtures_dir / "native_text.pdf", store)
    library.index_path.write_text('{"version": 999, "pages": []}\n', encoding="utf-8")
    with pytest.raises(StandardStoreCorruptError):
        StandardMatcher(library).match(
            _encode(np.zeros((100, 100, 3), dtype=np.uint8)), "image/png"
        )


def test_stale_standard_index_fails_closed(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library, manifest = _parse_and_register(fixtures_dir / "native_text.pdf", store)
    manifest_path = library.documents_dir / manifest.standard_id / "manifest.json"
    payload = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(
        payload.replace("fixture-reviewer", "reviewer-changed"), encoding="utf-8"
    )
    with pytest.raises(StandardStoreCorruptError, match="stale"):
        library.load_page_index()


def test_tampered_feature_file_fails_closed(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library, manifest = _parse_and_register(fixtures_dir / "native_text.pdf", store)
    fingerprint = manifest.page_fingerprints[0]
    feature_path = store.workspace / fingerprint.feature_ref
    feature_path.write_bytes(feature_path.read_bytes() + b"tamper")
    image = library.read_image(fingerprint.page_image_ref)
    with pytest.raises(StandardStoreCorruptError, match="digest mismatch"):
        StandardMatcher(library).match(_encode(image), "image/png")


def test_match_result_rejects_safe_decision_below_its_own_gate(
    fixtures_dir, tmp_path
) -> None:
    from pydantic import ValidationError

    store = ArtifactStore(tmp_path / "var")
    library, manifest = _parse_and_register(fixtures_dir / "native_text.pdf", store)
    image = library.read_image(manifest.page_fingerprints[0].page_image_ref)
    result = StandardMatcher(library).match(_encode(image), "image/png")
    payload = result.model_dump(mode="python")
    payload["threshold"] = 1.0
    payload["top1_score"] = 0.9
    payload["candidates"][0]["scores"]["combined"] = 0.9
    payload["margin"] = max(0.0, 0.9 - payload["top2_score"])
    with pytest.raises(ValidationError, match="below the configured threshold"):
        type(result).model_validate(payload)


def test_standard_manifest_rejects_pipeline_mismatch(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library, manifest = _parse_and_register(fixtures_dir / "native_text.pdf", store)
    manifest_path = library.documents_dir / manifest.standard_id / "manifest.json"
    payload = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(
        payload.replace(
            library.fingerprint_pipeline_digest,
            "f" * 64,
        ),
        encoding="utf-8",
    )
    with pytest.raises(StandardStoreCorruptError, match="pipeline"):
        library.read_manifest(manifest.standard_id)


def test_matcher_rejects_invalid_threshold_configuration(tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library = StandardLibrary(store)
    with pytest.raises(ValueError, match="high_threshold"):
        StandardMatcher(library, high_threshold=-0.1)


def test_tampered_standard_document_fails_closed(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library, manifest = _parse_and_register(fixtures_dir / "native_text.pdf", store)
    document_path = library.documents_dir / manifest.standard_id / "document.json"
    document_path.write_text(
        document_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(StandardStoreCorruptError, match="file digest mismatch"):
        library.read_document(manifest.standard_id)


def test_tampered_standard_page_image_fails_when_verified(fixtures_dir, tmp_path) -> None:
    store = ArtifactStore(tmp_path / "var")
    library, manifest = _parse_and_register(fixtures_dir / "native_text.pdf", store)
    fingerprint = manifest.page_fingerprints[0]
    image_path = store.workspace / fingerprint.page_image_ref
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    assert image is not None
    image[0:10, 0:10] = 0
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    image_path.write_bytes(encoded.tobytes())
    with pytest.raises(StandardStoreCorruptError, match="pixel digest mismatch"):
        library.read_image(
            fingerprint.page_image_ref,
            expected_pixel_sha256=fingerprint.page_image_sha256,
        )
