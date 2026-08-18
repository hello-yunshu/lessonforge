from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from document_intelligence.exceptions import ProductionStoreCorruptError
from document_intelligence.production import (
    DatasetQualificationRequest,
    EvidenceOrigin,
    LicenseQualificationRequest,
    LicenseResolution,
    ParserQualificationRequest,
    PilotQualificationRequest,
    ProductionQualificationPolicy,
    ProductionQualificationRequest,
    ProductionQualificationService,
    ProductionQualificationStore,
    QualificationDatasetRole,
    ScaleQualificationRequest,
    SupplyChainQualificationRequest,
)

H = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64


def policy() -> ProductionQualificationPolicy:
    return ProductionQualificationPolicy(
        minimum_domains=2,
        minimum_gold_documents=2,
        minimum_challenge_documents=2,
        minimum_parser_accuracy=0.9,
        maximum_parser_timeout_rate=0.01,
        maximum_parser_failure_rate=0.01,
        minimum_deterministic_replay_rate=1.0,
        minimum_soak_hours=1,
        minimum_scale_concurrency=2,
        minimum_scale_documents=4,
        maximum_scale_error_rate=0.01,
        minimum_branch_coverage=80,
        minimum_pilot_days=1,
        minimum_pilot_documents=2,
        minimum_pilot_expert_reviews=2,
        minimum_pilot_accuracy=0.9,
    )


def service(tmp_path: Path) -> ProductionQualificationService:
    return ProductionQualificationService(
        ProductionQualificationStore(tmp_path), policy()
    )


def dataset_request(
    role: QualificationDatasetRole,
    *,
    snapshot: str,
    origin: EvidenceOrigin = EvidenceOrigin.REAL,
) -> DatasetQualificationRequest:
    return DatasetQualificationRequest(
        dataset_name=f"real-{role.value}",
        role=role,
        origin=origin,
        domain_families=["academic-paper", "education-content"],
        document_count=2,
        page_count=10,
        modalities=["native-pdf", "scanned-pdf"],
        edge_cases=["multi-column", "cross-page"],
        manifest_sha256=H,
        schema_sha256=B,
        content_snapshot_sha256=snapshot,
        evidence_sha256=C,
        expert_approved=True,
        approver_id_hash=D,
        privacy_reviewed=True,
        license_reviewed=True,
    )


def full_chain(tmp_path: Path) -> tuple[ProductionQualificationService, dict[str, str]]:
    svc = service(tmp_path)
    gold = svc.record_dataset(
        dataset_request(QualificationDatasetRole.GOLD, snapshot=E)
    )
    challenge = svc.record_dataset(
        dataset_request(QualificationDatasetRole.CHALLENGE, snapshot=F)
    )
    parser = svc.record_parser(
        ParserQualificationRequest(
            parser_id="paddle",
            parser_version="3.7.0",
            runtime_artifact_sha256=H,
            model_artifact_sha256=B,
            container_image_sha256=C,
            config_sha256=D,
            gold_dataset_evidence_id=gold.evidence_id,
            challenge_dataset_evidence_id=challenge.evidence_id,
            accuracy=0.95,
            family_accuracy={"academic-paper": 0.94, "education-content": 0.96},
            p0_errors=0,
            p1_errors=0,
            severe_error_rate=0,
            timeout_rate=0,
            failure_rate=0,
            deterministic_replay_rate=1,
            license_resolution=LicenseResolution.OPEN_SOURCE_COMPLIANT,
            evidence_sha256=E,
        )
    )
    scale = svc.record_scale(
        ScaleQualificationRequest(
            workload_profile="phase10-test",
            environment_sha256=H,
            source_commit_sha="a" * 40,
            duration_hours=2,
            max_concurrency=2,
            document_count=4,
            page_count=20,
            latency_ms_p95=100,
            latency_ms_p99=200,
            peak_rss_mb=512,
            peak_disk_mb=1024,
            error_rate=0,
            duplicate_side_effects=0,
            restart_recovery_passed=True,
            idempotency_passed=True,
            disk_full_recovery_passed=True,
            corrupted_record_detection_passed=True,
            index_rebuild_passed=True,
            evidence_sha256=B,
        )
    )
    supply = svc.record_supply_chain(
        SupplyChainQualificationRequest(
            source_commit_sha="a" * 40,
            ci_provider="github-actions",
            ci_run_identity_sha256=H,
            ruff_passed=True,
            mypy_passed=True,
            tests_passed=True,
            test_count=220,
            branch_coverage=81,
            sbom_sha256=B,
            vulnerability_scan_sha256=C,
            critical_vulnerabilities=0,
            high_vulnerabilities=0,
            license_scan_sha256=D,
            container_image_sha256=E,
            reproducible_build_passed=True,
            release_signature_verified=True,
            release_artifact_sha256=F,
            evidence_sha256=H,
        )
    )
    license_record = svc.record_license(
        LicenseQualificationRequest(
            component="PyMuPDF",
            resolution=LicenseResolution.COMMERCIAL,
            distribution_mode="closed-source-commercial",
            license_name="commercial-license",
            legal_reviewed=True,
            evidence_sha256=H,
        )
    )
    pilot = svc.record_pilot(
        PilotQualificationRequest(
            pilot_name="limited-real-pilot",
            origin=EvidenceOrigin.REAL,
            domain_families=["education-content"],
            duration_days=2,
            document_count=3,
            expert_reviewed_count=2,
            accuracy=0.95,
            p0_errors=0,
            p1_errors=0,
            severe_error_rate=0,
            human_edit_seconds_p95=30,
            rollback_drill_passed=True,
            incident_count=0,
            unresolved_high_severity_incidents=0,
            evidence_sha256=F,
        )
    )
    return svc, {
        "gold": gold.evidence_id,
        "challenge": challenge.evidence_id,
        "parser": parser.evidence_id,
        "scale": scale.evidence_id,
        "supply": supply.evidence_id,
        "license": license_record.evidence_id,
        "pilot": pilot.evidence_id,
    }


def qualify_request(ids: dict[str, str]) -> ProductionQualificationRequest:
    return ProductionQualificationRequest(
        dataset_evidence_ids=[ids["gold"], ids["challenge"]],
        parser_evidence_ids=[ids["parser"]],
        scale_evidence_id=ids["scale"],
        supply_chain_evidence_id=ids["supply"],
        license_evidence_ids=[ids["license"]],
        pilot_evidence_id=ids["pilot"],
        requested_by_id_hash=H,
    )


def test_complete_real_chain_can_qualify_but_never_auto_releases(tmp_path: Path) -> None:
    svc, ids = full_chain(tmp_path)
    report = svc.qualify(qualify_request(ids))
    assert report.qualified is True
    assert report.blocking_reasons == []
    assert report.automatic_release_authorized is False
    assert report.human_release_required is True
    assert report.bounded_auto is False
    assert svc.require_qualified(report.report_id) == report


def test_synthetic_dataset_is_persisted_as_blocked_evidence(tmp_path: Path) -> None:
    svc = service(tmp_path)
    record = svc.record_dataset(
        dataset_request(
            QualificationDatasetRole.GOLD,
            snapshot=E,
            origin=EvidenceOrigin.SYNTHETIC,
        )
    )
    assert record.passed is False
    assert "DATASET_NOT_REAL" in record.blocking_reasons


def test_parser_requires_disjoint_qualified_protected_sets(tmp_path: Path) -> None:
    svc = service(tmp_path)
    gold = svc.record_dataset(dataset_request(QualificationDatasetRole.GOLD, snapshot=E))
    challenge = svc.record_dataset(
        dataset_request(QualificationDatasetRole.CHALLENGE, snapshot=E)
    )
    parser = svc.record_parser(
        ParserQualificationRequest(
            parser_id="opendoc",
            parser_version="0.1.0",
            runtime_artifact_sha256=H,
            model_artifact_sha256=B,
            container_image_sha256=C,
            config_sha256=D,
            gold_dataset_evidence_id=gold.evidence_id,
            challenge_dataset_evidence_id=challenge.evidence_id,
            accuracy=.99,
            family_accuracy={"academic-paper": .99, "education-content": .99},
            p0_errors=0,
            p1_errors=0,
            severe_error_rate=0,
            timeout_rate=0,
            failure_rate=0,
            deterministic_replay_rate=1,
            license_resolution=LicenseResolution.OPEN_SOURCE_COMPLIANT,
            evidence_sha256=F,
        )
    )
    assert parser.passed is False
    assert "PARSER_PROTECTED_DATASETS_NOT_DISJOINT" in parser.blocking_reasons


def test_store_rejects_tampered_record(tmp_path: Path) -> None:
    svc = service(tmp_path)
    record = svc.record_license(
        LicenseQualificationRequest(
            component="PyMuPDF",
            resolution=LicenseResolution.UNRESOLVED,
            distribution_mode="unknown",
            license_name="AGPL-or-commercial",
            legal_reviewed=False,
            evidence_sha256=H,
        )
    )
    path = (
        tmp_path
        / "production-qualification"
        / "licenses"
        / record.evidence_id
        / "record.json"
    )
    payload = json.loads(path.read_text())
    payload["legal_reviewed"] = True
    path.write_text(json.dumps(payload))
    with pytest.raises(ProductionStoreCorruptError):
        svc.store.read_license(record.evidence_id)


def test_immutable_idempotency_and_conflict_detection(tmp_path: Path) -> None:
    svc = service(tmp_path)
    request = LicenseQualificationRequest(
        component="PyMuPDF",
        resolution=LicenseResolution.COMMERCIAL,
        distribution_mode="closed",
        license_name="commercial",
        legal_reviewed=True,
        evidence_sha256=H,
    )
    first = svc.record_license(request)
    second = svc.record_license(request)
    assert first == second
    manifest = (
        tmp_path
        / "production-qualification"
        / "licenses"
        / first.evidence_id
        / "manifest.json"
    )
    envelope = json.loads(manifest.read_text())
    assert envelope["semantic_sha256"] == first.semantic_digest()


def test_policy_digest_changes_report_identity(tmp_path: Path) -> None:
    svc, ids = full_chain(tmp_path)
    first = svc.qualify(qualify_request(ids))
    other = ProductionQualificationService(
        svc.store,
        ProductionQualificationPolicy(**{**policy().__dict__, "minimum_pilot_days": 3}),
    )
    second = other.qualify(qualify_request(ids))
    assert first.report_id != second.report_id
    assert second.qualified is False
    assert "PILOT_DURATION_BELOW_MINIMUM" in second.blocking_reasons


def test_current_policy_rechecks_parser_family_accuracy(tmp_path: Path) -> None:
    svc, ids = full_chain(tmp_path)
    assert svc.qualify(qualify_request(ids)).qualified is True
    stricter = ProductionQualificationService(
        svc.store,
        ProductionQualificationPolicy(
            **{**policy().__dict__, "minimum_parser_accuracy": 0.97}
        ),
    )
    report = stricter.qualify(qualify_request(ids))
    assert report.qualified is False
    assert "PARSER_FAMILY_ACCURACY_BELOW_MINIMUM" in report.blocking_reasons
