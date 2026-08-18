from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from document_intelligence.campaign import (
    CampaignActorRequest,
    CampaignEvidenceKind,
    CampaignFinalizeRequest,
    CampaignState,
    CampaignStore,
    EvidenceLinkRequest,
    QualificationCampaignService,
    StepCheckpointRequest,
    StepClaimRequest,
    StepTransitionRequest,
)
from document_intelligence.exceptions import QualificationCampaignGateError
from document_intelligence.production import (
    DatasetQualificationRequest,
    EvidenceOrigin,
    LicenseQualificationRequest,
    LicenseResolution,
    ParserQualificationRequest,
    PilotQualificationRequest,
    ProductionQualificationPolicy,
    ProductionQualificationService,
    ProductionQualificationStore,
    QualificationDatasetRole,
    ScaleQualificationRequest,
    SupplyChainQualificationRequest,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "docs/phase-11/benchmark_results.json"
OUT_MD = ROOT / "docs/phase-11/QUALIFICATION_CAMPAIGN_BENCHMARK.md"

H = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64


def production_policy() -> ProductionQualificationPolicy:
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


def dataset_request(
    role: QualificationDatasetRole, *, snapshot: str
) -> DatasetQualificationRequest:
    return DatasetQualificationRequest(
        dataset_name=f"real-{role.value}",
        role=role,
        origin=EvidenceOrigin.REAL,
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


def full_chain(
    root: Path,
) -> tuple[ProductionQualificationService, dict[str, str]]:
    service = ProductionQualificationService(
        ProductionQualificationStore(root), production_policy()
    )
    gold = service.record_dataset(
        dataset_request(QualificationDatasetRole.GOLD, snapshot=E)
    )
    challenge = service.record_dataset(
        dataset_request(QualificationDatasetRole.CHALLENGE, snapshot=F)
    )
    parser = service.record_parser(
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
    scale = service.record_scale(
        ScaleQualificationRequest(
            workload_profile="phase11-test",
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
    supply = service.record_supply_chain(
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
    license_record = service.record_license(
        LicenseQualificationRequest(
            component="PyMuPDF",
            resolution=LicenseResolution.COMMERCIAL,
            distribution_mode="closed-source-commercial",
            license_name="commercial-license",
            legal_reviewed=True,
            evidence_sha256=H,
        )
    )
    pilot = service.record_pilot(
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
    return service, {
        "gold": gold.evidence_id,
        "challenge": challenge.evidence_id,
        "parser": parser.evidence_id,
        "scale": scale.evidence_id,
        "supply": supply.evidence_id,
        "license": license_record.evidence_id,
        "pilot": pilot.evidence_id,
    }


def complete_step(
    service: QualificationCampaignService,
    campaign_id: str,
    step_id: str,
    kind: CampaignEvidenceKind,
    evidence_id: str,
    now: datetime,
) -> None:
    snapshot = service.claim(
        campaign_id,
        step_id,
        StepClaimRequest(worker_id_hash=H, lease_seconds=300),
        now=now,
    )
    lease = next(item for item in snapshot.steps if item.step_id == step_id).lease
    if lease is None:
        raise RuntimeError("benchmark lease was not created")
    service.checkpoint(
        campaign_id,
        step_id,
        StepCheckpointRequest(
            worker_id_hash=H,
            lease_id=lease.lease_id,
            completed_units=1,
            total_units=1,
            cursor_sha256=H,
            metrics={"items": 1.0},
        ),
        now=now,
    )
    service.link_evidence(
        campaign_id,
        step_id,
        EvidenceLinkRequest(
            worker_id_hash=H,
            lease_id=lease.lease_id,
            evidence_kind=kind,
            evidence_id=evidence_id,
        ),
        now=now,
    )
    service.complete_step(
        campaign_id,
        step_id,
        StepTransitionRequest(worker_id_hash=H, lease_id=lease.lease_id),
        now=now,
    )


def main() -> None:
    checks: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="di-phase11-") as value:
        source = Path(value) / "source"
        production, ids = full_chain(source)
        service = QualificationCampaignService(CampaignStore(source), production)
        checks.append(
            {
                "name": "empty-campaign-store-has-no-qualification",
                "passed": service.inspect()["campaignCount"] == 0,
            }
        )
        unauthorized = service.default_request(
            campaign_name="unauthorized-plan",
            source_commit_sha="a" * 40,
            environment_sha256=H,
            policy_sha256=production.policy.digest(),
            created_by_id_hash=H,
        )
        unauthorized_manifest = service.create(unauthorized)
        try:
            service.start(
                unauthorized_manifest.campaign_id,
                CampaignActorRequest(actor_id_hash=H),
            )
        except QualificationCampaignGateError:
            authorization_blocked = True
        else:
            authorization_blocked = False
        checks.append(
            {
                "name": "external-data-authorization-required",
                "passed": authorization_blocked,
            }
        )
        request = service.default_request(
            campaign_name="phase11-benchmark",
            source_commit_sha="a" * 40,
            environment_sha256=H,
            policy_sha256=production.policy.digest(),
            created_by_id_hash=H,
        ).model_copy(update={"external_data_authorized": True})
        manifest = service.create(request)
        snapshot = service.start(
            manifest.campaign_id, CampaignActorRequest(actor_id_hash=H)
        )
        checks.append(
            {
                "name": "manifest-and-start-are-immutable",
                "passed": snapshot.state == CampaignState.RUNNING
                and snapshot.event_count == 1,
            }
        )
        try:
            service.claim(
                manifest.campaign_id,
                "parser",
                StepClaimRequest(worker_id_hash=H),
            )
        except QualificationCampaignGateError:
            dependency_blocked = True
        else:
            dependency_blocked = False
        checks.append(
            {
                "name": "dependency-order-is-enforced",
                "passed": dependency_blocked,
            }
        )
        now = datetime(2026, 8, 4, tzinfo=timezone.utc)
        chain = (
            ("gold", CampaignEvidenceKind.DATASET, ids["gold"]),
            ("challenge", CampaignEvidenceKind.DATASET, ids["challenge"]),
            ("parser", CampaignEvidenceKind.PARSER, ids["parser"]),
            ("scale", CampaignEvidenceKind.SCALE, ids["scale"]),
            ("supply", CampaignEvidenceKind.SUPPLY_CHAIN, ids["supply"]),
            ("license", CampaignEvidenceKind.LICENSE, ids["license"]),
            ("pilot", CampaignEvidenceKind.PILOT, ids["pilot"]),
        )
        for step_id, kind, evidence_id in chain:
            complete_step(
                service,
                manifest.campaign_id,
                step_id,
                kind,
                evidence_id,
                now,
            )
            now += timedelta(seconds=1)
        ready = service.snapshot(manifest.campaign_id)
        checks.append(
            {
                "name": "checkpoints-and-evidence-survive-replay",
                "passed": all(
                    item.state.value == "completed"
                    for item in ready.steps
                    if item.step_id != "qualification"
                ),
            }
        )
        completed = service.finalize(
            manifest.campaign_id,
            CampaignFinalizeRequest(actor_id_hash=H, requested_by_id_hash=H),
        )
        checks.append(
            {
                "name": "qualification-report-is-linked",
                "passed": completed.state == CampaignState.COMPLETED
                and completed.production_report_id is not None,
            }
        )
        checks.append(
            {
                "name": "qualification-never-authorizes-release",
                "passed": completed.automatic_release_authorized is False
                and completed.bounded_auto is False,
            }
        )
        bundle = Path(value) / "campaign.zip"
        exported = service.export_bundle(manifest.campaign_id, bundle)
        verified = service.verify_bundle(bundle)
        checks.append(
            {
                "name": "sealed-bundle-has-no-raw-documents",
                "passed": exported["bundle"]["contains_raw_documents"] is False
                and verified["verified"] is True,
            }
        )
        target = Path(value) / "target"
        target_production, _ = full_chain(target)
        restored_service = QualificationCampaignService(
            CampaignStore(target), target_production
        )
        restored = restored_service.import_bundle(bundle)
        restored_again = restored_service.import_bundle(bundle)
        checks.append(
            {
                "name": "bundle-restore-is-idempotent",
                "passed": restored.model_dump(mode="json")
                == restored_again.model_dump(mode="json")
                == completed.model_dump(mode="json"),
            }
        )
        events = service.store.read_events(manifest.campaign_id)
        checks.append(
            {
                "name": "event-chain-is-contiguous",
                "passed": all(event.sequence == index for index, event in enumerate(events, 1))
                and completed.last_event_sha256 == events[-1].chain_digest(),
            }
        )
    payload = {
        "phase": 11,
        "passed": all(bool(item["passed"]) for item in checks),
        "checks": checks,
        "production_evidence_origin": "deterministic-test-fixtures-only",
        "production_qualification_claimed": False,
        "automatic_release_authorized": False,
        "bounded_auto": False,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# Phase 11 生产资格活动编排基准",
        "",
        f"结论：**{'通过' if payload['passed'] else '不通过'}**",
        "",
        "| 检查 | 结果 |",
        "|---|---|",
    ]
    lines.extend(
        f"| {item['name']} | {'通过' if item['passed'] else '失败'} |"
        for item in checks
    )
    lines.extend(
        [
            "",
            "> 本基准只验证编排、恢复和门禁，不是现实生产资格证据。",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
