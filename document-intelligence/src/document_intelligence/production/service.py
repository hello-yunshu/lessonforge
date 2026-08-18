from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from document_intelligence.exceptions import ProductionQualificationGateError

from .models import (
    DatasetQualificationEvidence,
    DatasetQualificationRequest,
    EvidenceOrigin,
    LicenseQualificationEvidence,
    LicenseQualificationRequest,
    LicenseResolution,
    ParserQualificationEvidence,
    ParserQualificationRequest,
    PilotQualificationEvidence,
    PilotQualificationRequest,
    ProductionQualificationReport,
    ProductionQualificationRequest,
    QualificationDatasetRole,
    QualificationStatus,
    ScaleQualificationEvidence,
    ScaleQualificationRequest,
    SupplyChainQualificationEvidence,
    SupplyChainQualificationRequest,
    stable_production_id,
)
from .store import ProductionQualificationStore


@dataclass(frozen=True)
class ProductionQualificationPolicy:
    minimum_domains: int = 3
    minimum_gold_documents: int = 100
    minimum_challenge_documents: int = 50
    minimum_parser_accuracy: float = 0.90
    maximum_parser_timeout_rate: float = 0.01
    maximum_parser_failure_rate: float = 0.01
    minimum_deterministic_replay_rate: float = 1.0
    minimum_soak_hours: float = 168.0
    minimum_scale_concurrency: int = 8
    minimum_scale_documents: int = 10000
    maximum_scale_error_rate: float = 0.01
    minimum_branch_coverage: float = 80.0
    minimum_pilot_days: float = 7.0
    minimum_pilot_documents: int = 500
    minimum_pilot_expert_reviews: int = 100
    minimum_pilot_accuracy: float = 0.90
    required_license_components: tuple[str, ...] = ("pymupdf",)

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class ProductionQualificationService:
    def __init__(
        self,
        store: ProductionQualificationStore,
        policy: ProductionQualificationPolicy,
    ) -> None:
        self.store = store
        self.policy = policy

    def record_dataset(self, request: DatasetQualificationRequest) -> DatasetQualificationEvidence:
        blockers: list[str] = []
        if request.origin != EvidenceOrigin.REAL:
            blockers.append("DATASET_NOT_REAL")
        if not request.expert_approved or request.approver_id_hash is None:
            blockers.append("DATASET_NOT_EXPERT_APPROVED")
        if not request.privacy_reviewed:
            blockers.append("DATASET_PRIVACY_REVIEW_MISSING")
        if not request.license_reviewed:
            blockers.append("DATASET_LICENSE_REVIEW_MISSING")
        minimum = (
            self.policy.minimum_gold_documents
            if request.role == QualificationDatasetRole.GOLD
            else self.policy.minimum_challenge_documents
        )
        if request.document_count < minimum:
            blockers.append("DATASET_DOCUMENT_COUNT_BELOW_MINIMUM")
        if len(request.domain_families) < self.policy.minimum_domains:
            blockers.append("DATASET_DOMAIN_COVERAGE_BELOW_MINIMUM")
        evidence_id = stable_production_id("dataset", request.semantic_digest())
        return self.store.commit_dataset(
            DatasetQualificationEvidence(
                evidence_id=evidence_id,
                **request.model_dump(mode="python"),
                passed=not blockers,
                blocking_reasons=sorted(blockers),
            )
        )

    def record_parser(self, request: ParserQualificationRequest) -> ParserQualificationEvidence:
        gold = self.store.read_dataset(request.gold_dataset_evidence_id)
        challenge = self.store.read_dataset(request.challenge_dataset_evidence_id)
        blockers: list[str] = []
        if gold.role != QualificationDatasetRole.GOLD or not gold.passed:
            blockers.append("PARSER_GOLD_DATASET_NOT_QUALIFIED")
        if challenge.role != QualificationDatasetRole.CHALLENGE or not challenge.passed:
            blockers.append("PARSER_CHALLENGE_DATASET_NOT_QUALIFIED")
        if gold.content_snapshot_sha256 == challenge.content_snapshot_sha256:
            blockers.append("PARSER_PROTECTED_DATASETS_NOT_DISJOINT")
        if request.accuracy < self.policy.minimum_parser_accuracy:
            blockers.append("PARSER_ACCURACY_BELOW_MINIMUM")
        if request.p0_errors:
            blockers.append("PARSER_P0_ERRORS")
        if request.p1_errors:
            blockers.append("PARSER_P1_ERRORS")
        if request.severe_error_rate > 0:
            blockers.append("PARSER_SEVERE_ERRORS")
        if request.timeout_rate > self.policy.maximum_parser_timeout_rate:
            blockers.append("PARSER_TIMEOUT_RATE_OVER_LIMIT")
        if request.failure_rate > self.policy.maximum_parser_failure_rate:
            blockers.append("PARSER_FAILURE_RATE_OVER_LIMIT")
        if request.deterministic_replay_rate < self.policy.minimum_deterministic_replay_rate:
            blockers.append("PARSER_REPLAY_NOT_DETERMINISTIC")
        if request.license_resolution == LicenseResolution.UNRESOLVED:
            blockers.append("PARSER_LICENSE_UNRESOLVED")
        if set(request.family_accuracy) != set(gold.domain_families):
            blockers.append("PARSER_FAMILY_METRICS_INCOMPLETE")
        elif min(request.family_accuracy.values()) < self.policy.minimum_parser_accuracy:
            blockers.append("PARSER_FAMILY_ACCURACY_BELOW_MINIMUM")
        evidence_id = stable_production_id("parser", request.semantic_digest())
        return self.store.commit_parser(
            ParserQualificationEvidence(
                evidence_id=evidence_id,
                **request.model_dump(mode="python"),
                passed=not blockers,
                blocking_reasons=sorted(blockers),
            )
        )

    def record_scale(self, request: ScaleQualificationRequest) -> ScaleQualificationEvidence:
        blockers: list[str] = []
        if request.duration_hours < self.policy.minimum_soak_hours:
            blockers.append("SOAK_DURATION_BELOW_MINIMUM")
        if request.max_concurrency < self.policy.minimum_scale_concurrency:
            blockers.append("SCALE_CONCURRENCY_BELOW_MINIMUM")
        if request.document_count < self.policy.minimum_scale_documents:
            blockers.append("SCALE_DOCUMENT_COUNT_BELOW_MINIMUM")
        if request.error_rate > self.policy.maximum_scale_error_rate:
            blockers.append("SCALE_ERROR_RATE_OVER_LIMIT")
        if request.duplicate_side_effects:
            blockers.append("SCALE_DUPLICATE_SIDE_EFFECTS")
        recovery_checks = {
            "RESTART_RECOVERY_FAILED": request.restart_recovery_passed,
            "IDEMPOTENCY_FAILED": request.idempotency_passed,
            "DISK_FULL_RECOVERY_FAILED": request.disk_full_recovery_passed,
            "CORRUPT_RECORD_DETECTION_FAILED": request.corrupted_record_detection_passed,
            "INDEX_REBUILD_FAILED": request.index_rebuild_passed,
        }
        blockers.extend(code for code, passed in recovery_checks.items() if not passed)
        evidence_id = stable_production_id("scale", request.semantic_digest())
        return self.store.commit_scale(
            ScaleQualificationEvidence(
                evidence_id=evidence_id,
                **request.model_dump(mode="python"),
                passed=not blockers,
                blocking_reasons=sorted(blockers),
            )
        )

    def record_supply_chain(
        self, request: SupplyChainQualificationRequest
    ) -> SupplyChainQualificationEvidence:
        blockers: list[str] = []
        checks = {
            "RUFF_EVIDENCE_FAILED": request.ruff_passed,
            "MYPY_EVIDENCE_FAILED": request.mypy_passed,
            "TEST_EVIDENCE_FAILED": request.tests_passed,
            "REPRODUCIBLE_BUILD_FAILED": request.reproducible_build_passed,
            "RELEASE_SIGNATURE_UNVERIFIED": request.release_signature_verified,
        }
        blockers.extend(code for code, passed in checks.items() if not passed)
        if request.branch_coverage < self.policy.minimum_branch_coverage:
            blockers.append("BRANCH_COVERAGE_BELOW_MINIMUM")
        if request.critical_vulnerabilities:
            blockers.append("CRITICAL_VULNERABILITIES_PRESENT")
        if request.high_vulnerabilities:
            blockers.append("HIGH_VULNERABILITIES_PRESENT")
        evidence_id = stable_production_id("supply", request.semantic_digest())
        return self.store.commit_supply_chain(
            SupplyChainQualificationEvidence(
                evidence_id=evidence_id,
                **request.model_dump(mode="python"),
                passed=not blockers,
                blocking_reasons=sorted(blockers),
            )
        )

    def record_license(self, request: LicenseQualificationRequest) -> LicenseQualificationEvidence:
        blockers: list[str] = []
        if not request.legal_reviewed:
            blockers.append("LICENSE_LEGAL_REVIEW_MISSING")
        if request.resolution == LicenseResolution.UNRESOLVED:
            blockers.append("LICENSE_UNRESOLVED")
        evidence_id = stable_production_id("license", request.semantic_digest())
        return self.store.commit_license(
            LicenseQualificationEvidence(
                evidence_id=evidence_id,
                **request.model_dump(mode="python"),
                passed=not blockers,
                blocking_reasons=sorted(blockers),
            )
        )

    def record_pilot(self, request: PilotQualificationRequest) -> PilotQualificationEvidence:
        blockers: list[str] = []
        if request.origin != EvidenceOrigin.REAL:
            blockers.append("PILOT_NOT_REAL")
        if request.duration_days < self.policy.minimum_pilot_days:
            blockers.append("PILOT_DURATION_BELOW_MINIMUM")
        if request.document_count < self.policy.minimum_pilot_documents:
            blockers.append("PILOT_DOCUMENT_COUNT_BELOW_MINIMUM")
        if request.expert_reviewed_count < self.policy.minimum_pilot_expert_reviews:
            blockers.append("PILOT_EXPERT_REVIEW_BELOW_MINIMUM")
        if request.accuracy < self.policy.minimum_pilot_accuracy:
            blockers.append("PILOT_ACCURACY_BELOW_MINIMUM")
        if request.p0_errors:
            blockers.append("PILOT_P0_ERRORS")
        if request.p1_errors:
            blockers.append("PILOT_P1_ERRORS")
        if request.severe_error_rate > 0:
            blockers.append("PILOT_SEVERE_ERRORS")
        if not request.rollback_drill_passed:
            blockers.append("PILOT_ROLLBACK_DRILL_FAILED")
        if request.unresolved_high_severity_incidents:
            blockers.append("PILOT_HIGH_SEVERITY_INCIDENTS_OPEN")
        evidence_id = stable_production_id("pilot", request.semantic_digest())
        return self.store.commit_pilot(
            PilotQualificationEvidence(
                evidence_id=evidence_id,
                **request.model_dump(mode="python"),
                passed=not blockers,
                blocking_reasons=sorted(blockers),
            )
        )

    def qualify(self, request: ProductionQualificationRequest) -> ProductionQualificationReport:
        datasets = [self.store.read_dataset(item) for item in request.dataset_evidence_ids]
        parsers = [self.store.read_parser(item) for item in request.parser_evidence_ids]
        scale = self.store.read_scale(request.scale_evidence_id)
        supply = self.store.read_supply_chain(request.supply_chain_evidence_id)
        licenses = [self.store.read_license(item) for item in request.license_evidence_ids]
        pilot = self.store.read_pilot(request.pilot_evidence_id)
        blockers: list[str] = []
        gold = [item for item in datasets if item.role == QualificationDatasetRole.GOLD]
        challenge = [item for item in datasets if item.role == QualificationDatasetRole.CHALLENGE]
        if len(gold) != 1 or len(challenge) != 1:
            blockers.append("EXACTLY_ONE_GOLD_AND_CHALLENGE_REQUIRED")
        for item in datasets:
            if not item.passed:
                blockers.append("DATASET_EVIDENCE_BLOCKED")
            if item.origin != EvidenceOrigin.REAL:
                blockers.append("DATASET_NOT_REAL")
            minimum = (
                self.policy.minimum_gold_documents
                if item.role == QualificationDatasetRole.GOLD
                else self.policy.minimum_challenge_documents
            )
            if item.document_count < minimum:
                blockers.append("DATASET_DOCUMENT_COUNT_BELOW_MINIMUM")
            if len(item.domain_families) < self.policy.minimum_domains:
                blockers.append("DATASET_DOMAIN_COVERAGE_BELOW_MINIMUM")
        if gold and challenge:
            if gold[0].content_snapshot_sha256 == challenge[0].content_snapshot_sha256:
                blockers.append("PROTECTED_DATASETS_NOT_DISJOINT")
            if not set(challenge[0].domain_families).issubset(
                set(gold[0].domain_families)
            ):
                blockers.append("CHALLENGE_DOMAINS_NOT_COVERED_BY_GOLD")
        if not parsers:
            blockers.append("EXTERNAL_PARSER_EVIDENCE_MISSING")
        for item in parsers:
            if not item.passed:
                blockers.append("PARSER_EVIDENCE_BLOCKED")
            if item.accuracy < self.policy.minimum_parser_accuracy:
                blockers.append("PARSER_ACCURACY_BELOW_MINIMUM")
            if item.timeout_rate > self.policy.maximum_parser_timeout_rate:
                blockers.append("PARSER_TIMEOUT_RATE_OVER_LIMIT")
            if item.failure_rate > self.policy.maximum_parser_failure_rate:
                blockers.append("PARSER_FAILURE_RATE_OVER_LIMIT")
            if item.deterministic_replay_rate < self.policy.minimum_deterministic_replay_rate:
                blockers.append("PARSER_REPLAY_NOT_DETERMINISTIC")
            if item.p0_errors or item.p1_errors or item.severe_error_rate > 0:
                blockers.append("PARSER_CRITICAL_ERRORS")
            if set(item.family_accuracy) != set(gold[0].domain_families if gold else []):
                blockers.append("PARSER_FAMILY_METRICS_INCOMPLETE")
            elif min(item.family_accuracy.values()) < self.policy.minimum_parser_accuracy:
                blockers.append("PARSER_FAMILY_ACCURACY_BELOW_MINIMUM")
        dataset_ids = set(request.dataset_evidence_ids)
        for parser in parsers:
            if {
                parser.gold_dataset_evidence_id,
                parser.challenge_dataset_evidence_id,
            } - dataset_ids:
                blockers.append("PARSER_DATASET_LINEAGE_NOT_INCLUDED")
        if not scale.passed:
            blockers.append("SCALE_EVIDENCE_BLOCKED")
        if scale.duration_hours < self.policy.minimum_soak_hours:
            blockers.append("SOAK_DURATION_BELOW_MINIMUM")
        if scale.max_concurrency < self.policy.minimum_scale_concurrency:
            blockers.append("SCALE_CONCURRENCY_BELOW_MINIMUM")
        if scale.document_count < self.policy.minimum_scale_documents:
            blockers.append("SCALE_DOCUMENT_COUNT_BELOW_MINIMUM")
        if scale.error_rate > self.policy.maximum_scale_error_rate:
            blockers.append("SCALE_ERROR_RATE_OVER_LIMIT")
        if not supply.passed:
            blockers.append("SUPPLY_CHAIN_EVIDENCE_BLOCKED")
        if supply.source_commit_sha != scale.source_commit_sha:
            blockers.append("SCALE_AND_SUPPLY_CHAIN_SOURCE_COMMIT_MISMATCH")
        if supply.branch_coverage < self.policy.minimum_branch_coverage:
            blockers.append("BRANCH_COVERAGE_BELOW_MINIMUM")
        if not pilot.passed:
            blockers.append("PILOT_EVIDENCE_BLOCKED")
        if pilot.duration_days < self.policy.minimum_pilot_days:
            blockers.append("PILOT_DURATION_BELOW_MINIMUM")
        if pilot.document_count < self.policy.minimum_pilot_documents:
            blockers.append("PILOT_DOCUMENT_COUNT_BELOW_MINIMUM")
        if pilot.expert_reviewed_count < self.policy.minimum_pilot_expert_reviews:
            blockers.append("PILOT_EXPERT_REVIEW_BELOW_MINIMUM")
        if pilot.accuracy < self.policy.minimum_pilot_accuracy:
            blockers.append("PILOT_ACCURACY_BELOW_MINIMUM")
        if gold and not set(pilot.domain_families).issubset(set(gold[0].domain_families)):
            blockers.append("PILOT_DOMAIN_NOT_COVERED_BY_GOLD")
        normalized_components = [item.component.casefold() for item in licenses]
        if len(normalized_components) != len(set(normalized_components)):
            blockers.append("CONFLICTING_LICENSE_EVIDENCE")
        license_by_component = {item.component.casefold(): item for item in licenses}
        for component in self.policy.required_license_components:
            evidence = license_by_component.get(component.casefold())
            if evidence is None:
                blockers.append(f"REQUIRED_LICENSE_EVIDENCE_MISSING:{component}")
            elif not evidence.passed:
                blockers.append(f"REQUIRED_LICENSE_EVIDENCE_BLOCKED:{component}")
        blockers.extend("LICENSE_EVIDENCE_BLOCKED" for item in licenses if not item.passed)
        unique = sorted(set(blockers))
        report_id = stable_production_id(
            "production",
            request.semantic_digest(),
            self.policy.digest(),
        )
        qualified = not unique
        return self.store.commit_report(
            ProductionQualificationReport(
                report_id=report_id,
                policy_sha256=self.policy.digest(),
                **request.model_dump(mode="python"),
                status=(
                    QualificationStatus.QUALIFIED
                    if qualified
                    else QualificationStatus.BLOCKED
                ),
                qualified=qualified,
                blocking_reasons=unique,
            )
        )

    def require_qualified(self, report_id: str) -> ProductionQualificationReport:
        report = self.store.read_report(report_id)
        if not report.qualified:
            raise ProductionQualificationGateError(
                "production qualification report is blocked"
            )
        return report

    def inspect(self) -> dict[str, object]:
        reports = self.store.list_reports()
        return {
            "schemaVersion": "1.0",
            "policySha256": self.policy.digest(),
            "datasetEvidenceCount": len(self.store.list_datasets()),
            "parserEvidenceCount": len(self.store.list_parsers()),
            "scaleEvidenceCount": len(self.store.list_scale()),
            "supplyChainEvidenceCount": len(self.store.list_supply_chain()),
            "licenseEvidenceCount": len(self.store.list_licenses()),
            "pilotEvidenceCount": len(self.store.list_pilots()),
            "reportCount": len(reports),
            "qualifiedReportCount": sum(1 for item in reports if item.qualified),
            "automaticReleaseAuthorized": False,
            "humanReleaseRequired": True,
            "boundedAuto": False,
        }
