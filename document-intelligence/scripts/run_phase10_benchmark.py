from __future__ import annotations

import json
import tempfile
from pathlib import Path

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

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "docs/phase-10/benchmark_results.json"
OUT_MD = ROOT / "docs/phase-10/PRODUCTION_QUALIFICATION_BENCHMARK.md"
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
        minimum_soak_hours=1,
        minimum_scale_concurrency=2,
        minimum_scale_documents=4,
        minimum_pilot_days=1,
        minimum_pilot_documents=2,
        minimum_pilot_expert_reviews=2,
    )


def dataset(role: QualificationDatasetRole, snapshot: str) -> DatasetQualificationRequest:
    return DatasetQualificationRequest(
        dataset_name=f"benchmark-{role.value}",
        role=role,
        origin=EvidenceOrigin.REAL,
        domain_families=["academic-paper", "education-content"],
        document_count=2,
        page_count=8,
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


def main() -> None:
    checks: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="di-phase10-") as value:
        service = ProductionQualificationService(
            ProductionQualificationStore(Path(value) / "var"), policy()
        )
        checks.append(
            {
                "name": "empty-store-not-qualified",
                "passed": service.inspect()["qualifiedReportCount"] == 0,
            }
        )
        synthetic = dataset(QualificationDatasetRole.GOLD, E).model_copy(
            update={"origin": EvidenceOrigin.SYNTHETIC}
        )
        synthetic_record = service.record_dataset(synthetic)
        checks.append(
            {
                "name": "synthetic-data-cannot-qualify",
                "passed": not synthetic_record.passed,
            }
        )
        gold = service.record_dataset(dataset(QualificationDatasetRole.GOLD, E))
        challenge = service.record_dataset(
            dataset(QualificationDatasetRole.CHALLENGE, F)
        )
        checks.append(
            {
                "name": "real-protected-datasets-qualified",
                "passed": gold.passed and challenge.passed,
            }
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
                accuracy=.95,
                family_accuracy={"academic-paper": .95, "education-content": .95},
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
        checks.append(
            {
                "name": "fixed-parser-artifacts-qualified",
                "passed": parser.passed,
            }
        )
        scale = service.record_scale(
            ScaleQualificationRequest(
                workload_profile="benchmark",
                environment_sha256=H,
                source_commit_sha="a" * 40,
                duration_hours=2,
                max_concurrency=2,
                document_count=4,
                page_count=16,
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
        checks.append({"name": "scale-and-recovery-qualified", "passed": scale.passed})
        supply = service.record_supply_chain(
            SupplyChainQualificationRequest(
                source_commit_sha="a" * 40,
                ci_provider="github-actions",
                ci_run_identity_sha256=H,
                ruff_passed=True,
                mypy_passed=True,
                tests_passed=True,
                test_count=215,
                branch_coverage=80.5,
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
        checks.append({"name": "supply-chain-qualified", "passed": supply.passed})
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
        checks.append(
            {"name": "pymupdf-license-resolved", "passed": license_record.passed}
        )
        pilot = service.record_pilot(
            PilotQualificationRequest(
                pilot_name="benchmark-real-pilot",
                origin=EvidenceOrigin.REAL,
                domain_families=["education-content"],
                duration_days=2,
                document_count=3,
                expert_reviewed_count=2,
                accuracy=.95,
                p0_errors=0,
                p1_errors=0,
                severe_error_rate=0,
                human_edit_seconds_p95=20,
                rollback_drill_passed=True,
                incident_count=0,
                unresolved_high_severity_incidents=0,
                evidence_sha256=F,
            )
        )
        checks.append({"name": "real-pilot-qualified", "passed": pilot.passed})
        report = service.qualify(
            ProductionQualificationRequest(
                dataset_evidence_ids=[gold.evidence_id, challenge.evidence_id],
                parser_evidence_ids=[parser.evidence_id],
                scale_evidence_id=scale.evidence_id,
                supply_chain_evidence_id=supply.evidence_id,
                license_evidence_ids=[license_record.evidence_id],
                pilot_evidence_id=pilot.evidence_id,
                requested_by_id_hash=H,
            )
        )
        checks.append(
            {
                "name": "complete-chain-can-qualify",
                "passed": report.qualified and not report.blocking_reasons,
            }
        )
        checks.append(
            {
                "name": "qualification-never-auto-releases",
                "passed": (
                    report.automatic_release_authorized is False
                    and report.human_release_required is True
                    and report.bounded_auto is False
                ),
            }
        )
    payload = {
        "phase": 10,
        "synthetic": True,
        "production_claim": False,
        "passed": all(bool(item["passed"]) for item in checks),
        "checks": checks,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# Phase 10 生产资格门禁确定性基准",
        "",
        "> 本基准仅验证资格系统逻辑，不代表真实生产资格。",
        "",
        "| 检查 | 结果 |",
        "|---|---|",
    ]
    lines.extend(
        f"| {item['name']} | {'通过' if item['passed'] else '失败'} |"
        for item in checks
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
