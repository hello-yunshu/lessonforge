from __future__ import annotations

import json
from pathlib import Path

from document_intelligence.campaign import (
    CampaignBundleManifest,
    CampaignEvent,
    CampaignManifest,
    CampaignSnapshot,
)
from document_intelligence.domain_pack_sdk import (
    DocumentFamilyProfile,
    DomainPackManifest,
)
from document_intelligence.domain_regression import CrossDomainRegressionReport
from document_intelligence.domain_runtime import DomainResult
from document_intelligence.family import FamilyDetectionResult
from document_intelligence.freeze import (
    FreezeBenchmarkReport, FreezeManifest, FreezeVerification
)
from document_intelligence.review import (
    LabelUReviewExport, LabelUReviewSubmission, ReviewRecord
)
from document_intelligence.production import (
    DatasetQualificationEvidence,
    LicenseQualificationEvidence,
    ParserQualificationEvidence,
    PilotQualificationEvidence,
    ProductionQualificationReport,
    ScaleQualificationEvidence,
    SupplyChainQualificationEvidence,
)
from document_intelligence.matching import MatchResult, PageFingerprint, StandardDocumentManifest
from document_intelligence.mlops.models import (
    ActiveLearningBatch,
    AliasUpdateRecord,
    CandidateEvaluationReport,
    DatasetSnapshot,
    MLflowRunRecord,
    ModelCandidate,
    ReleaseApproval,
    RollbackRecord,
    ShadowValidationReport,
)
from document_intelligence.schema import ParsedDocument, ParserResult, ParseRun
from document_intelligence.structure import StructureResult
from document_intelligence.rill.models import (
    RillObserveEvent, ShadowEvaluation, ShadowFeedbackRecord, ShadowSnapshotRecord,
)
from document_intelligence.rill.assist_models import (
    AssistActivationRecord,
    AssistEvidenceAttestation,
    AssistExecutionRecord,
    AssistParserResumeRecord,
    AssistParserSuspensionRecord,
    AssistQualificationReport,
    AssistRevocationRecord,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "schema"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    models = {
        "parsed-document.schema.json": ParsedDocument,
        "parse-run.schema.json": ParseRun,
        "parser-result.schema.json": ParserResult,
        "domain-pack-manifest.schema.json": DomainPackManifest,
        "document-family-profile.schema.json": DocumentFamilyProfile,
        "family-detection-result.schema.json": FamilyDetectionResult,
        "cross-domain-regression-report.schema.json": CrossDomainRegressionReport,
        "domain-result.schema.json": DomainResult,
        "labelu-review-export.schema.json": LabelUReviewExport,
        "labelu-review-submission.schema.json": LabelUReviewSubmission,
        "review-record.schema.json": ReviewRecord,
        "page-fingerprint.schema.json": PageFingerprint,
        "standard-document-manifest.schema.json": StandardDocumentManifest,
        "match-result.schema.json": MatchResult,
        "structure-result.schema.json": StructureResult,
        "rill-observe-event.schema.json": RillObserveEvent,
        "rill-shadow-evaluation.schema.json": ShadowEvaluation,
        "rill-shadow-feedback.schema.json": ShadowFeedbackRecord,
        "rill-shadow-snapshot.schema.json": ShadowSnapshotRecord,
        "rill-assist-attestation.schema.json": AssistEvidenceAttestation,
        "rill-assist-qualification.schema.json": AssistQualificationReport,
        "rill-assist-activation.schema.json": AssistActivationRecord,
        "rill-assist-execution.schema.json": AssistExecutionRecord,
        "rill-assist-revocation.schema.json": AssistRevocationRecord,
        "rill-assist-parser-suspension.schema.json": AssistParserSuspensionRecord,
        "rill-assist-parser-resume.schema.json": AssistParserResumeRecord,
        "active-learning-batch.schema.json": ActiveLearningBatch,
        "dataset-snapshot.schema.json": DatasetSnapshot,
        "mlflow-run-record.schema.json": MLflowRunRecord,
        "model-candidate.schema.json": ModelCandidate,
        "candidate-evaluation.schema.json": CandidateEvaluationReport,
        "shadow-validation.schema.json": ShadowValidationReport,
        "release-approval.schema.json": ReleaseApproval,
        "model-alias-update.schema.json": AliasUpdateRecord,
        "model-rollback.schema.json": RollbackRecord,
        "freeze-manifest.schema.json": FreezeManifest,
        "freeze-verification.schema.json": FreezeVerification,
        "freeze-benchmark-report.schema.json": FreezeBenchmarkReport,
        "production-dataset-evidence.schema.json": DatasetQualificationEvidence,
        "production-parser-evidence.schema.json": ParserQualificationEvidence,
        "production-scale-evidence.schema.json": ScaleQualificationEvidence,
        "production-supply-chain-evidence.schema.json": SupplyChainQualificationEvidence,
        "production-license-evidence.schema.json": LicenseQualificationEvidence,
        "production-pilot-evidence.schema.json": PilotQualificationEvidence,
        "production-qualification-report.schema.json": ProductionQualificationReport,
        "qualification-campaign-manifest.schema.json": CampaignManifest,
        "qualification-campaign-event.schema.json": CampaignEvent,
        "qualification-campaign-snapshot.schema.json": CampaignSnapshot,
        "qualification-campaign-bundle.schema.json": CampaignBundleManifest,
    }
    for filename, model in models.items():
        (OUT / filename).write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
