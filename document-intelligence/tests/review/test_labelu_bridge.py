from __future__ import annotations

from pathlib import Path

import pytest

from document_intelligence.review import (
    LabelUReviewSubmission,
    ReviewedObject,
)
from document_intelligence.exceptions import DomainReviewError
from document_intelligence.review import DomainReviewService

from tests.domain_runtime.test_engine_service import build_service


def test_labelu_export_and_review_submission(tmp_path: Path) -> None:
    service, structure, _ = build_service(tmp_path)
    result = service.apply(structure.structure_id, "education-content")
    review = DomainReviewService(
        tmp_path / "var",
        service.artifact_store,
        service.structure_service,
        service,
    )
    export = review.export_labelu(result.domain_result_id)
    assert export.adapter == "labelu-json-v1"
    assert export.tasks[0].objects
    submission = LabelUReviewSubmission(
        export_id=export.export_id,
        domain_result_id=result.domain_result_id,
        source_domain_digest=result.semantic_digest(),
        reviewer="reviewer-1",
        review_level="reviewer",
        reason="checked",
        objects=[
            ReviewedObject(
                element_id=result.annotations[0].element_id,
                labels=[result.annotations[0].domain_type],
            )
        ],
    )
    record = review.submit_labelu(submission)
    assert review.get_review(record.review_id).reviewer == "reviewer-1"


def test_review_rejects_stale_or_unknown_labels(tmp_path: Path) -> None:
    service, structure, _ = build_service(tmp_path)
    result = service.apply(structure.structure_id, "education-content")
    review = DomainReviewService(
        tmp_path / "var", service.artifact_store, service.structure_service, service
    )
    export = review.export_labelu(result.domain_result_id)
    with pytest.raises(DomainReviewError, match="stale"):
        review.submit_labelu(
            LabelUReviewSubmission(
                export_id=export.export_id,
                domain_result_id=result.domain_result_id,
                source_domain_digest="0" * 64,
                reviewer="reviewer",
                review_level="reviewer",
                reason="bad",
            )
        )
    with pytest.raises(DomainReviewError, match="labels"):
        review.submit_labelu(
            LabelUReviewSubmission(
                export_id=export.export_id,
                domain_result_id=result.domain_result_id,
                source_domain_digest=result.semantic_digest(),
                reviewer="reviewer",
                review_level="reviewer",
                reason="bad label",
                objects=[
                    ReviewedObject(
                        element_id=result.annotations[0].element_id, labels=["unknown"]
                    )
                ],
            )
        )


def test_labelu_export_is_idempotent(tmp_path: Path) -> None:
    service, structure, _ = build_service(tmp_path)
    result = service.apply(structure.structure_id, "education-content")
    review = DomainReviewService(
        tmp_path / "var", service.artifact_store, service.structure_service, service
    )
    first = review.export_labelu(result.domain_result_id)
    second = review.export_labelu(result.domain_result_id)
    assert second.model_dump(mode="json") == first.model_dump(mode="json")


def test_review_export_tampering_is_detected(tmp_path: Path) -> None:
    service, structure, _ = build_service(tmp_path)
    result = service.apply(structure.structure_id, "education-content")
    review = DomainReviewService(
        tmp_path / "var", service.artifact_store, service.structure_service, service
    )
    export = review.export_labelu(result.domain_result_id)
    result_path = review.root / "exports" / export.export_id / "result.json"
    result_path.write_text("{}", encoding="utf-8")
    with pytest.raises(DomainReviewError, match="digest verification"):
        review.export_labelu(result.domain_result_id)


def test_review_submission_must_match_export_digest(tmp_path: Path, monkeypatch) -> None:
    service, structure, _ = build_service(tmp_path)
    result = service.apply(structure.structure_id, "education-content")
    review = DomainReviewService(
        tmp_path / "var", service.artifact_store, service.structure_service, service
    )
    export = review.export_labelu(result.domain_result_id)
    original_read = review._read_record

    def altered(namespace: str, record_id: str):
        payload = original_read(namespace, record_id)
        if namespace == "exports":
            payload = dict(payload)
            payload["source_domain_digest"] = "f" * 64
        return payload

    monkeypatch.setattr(review, "_read_record", altered)
    with pytest.raises(DomainReviewError, match="differs from its review export"):
        review.submit_labelu(
            LabelUReviewSubmission(
                export_id=export.export_id,
                domain_result_id=result.domain_result_id,
                source_domain_digest=result.semantic_digest(),
                reviewer="reviewer",
                review_level="reviewer",
                reason="digest check",
            )
        )


def test_review_record_path_traversal_is_rejected(tmp_path: Path) -> None:
    service, _, _ = build_service(tmp_path)
    review = DomainReviewService(
        tmp_path / "var", service.artifact_store, service.structure_service, service
    )
    with pytest.raises(ValueError, match="review_record_id"):
        review.get_review("../escape")


def test_review_record_manifest_tampering_is_detected(tmp_path: Path) -> None:
    service, structure, _ = build_service(tmp_path)
    result = service.apply(structure.structure_id, "education-content")
    review = DomainReviewService(
        tmp_path / "var", service.artifact_store, service.structure_service, service
    )
    export = review.export_labelu(result.domain_result_id)
    manifest_path = review.root / "exports" / export.export_id / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    with pytest.raises(DomainReviewError, match="manifest is invalid"):
        review.export_labelu(result.domain_result_id)
