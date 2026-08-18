from __future__ import annotations


class DocumentIntelligenceError(Exception):
    """Base exception with a stable machine-readable error code."""

    code = "DOCUMENT_INTELLIGENCE_ERROR"
    severity = "P2"
    retryable = False
    http_status = 422


class UnsupportedInputError(DocumentIntelligenceError):
    code = "INPUT_UNSUPPORTED"
    http_status = 415


class CorruptInputError(DocumentIntelligenceError):
    code = "INPUT_CORRUPT"
    severity = "P1"
    http_status = 400


class ParserUnavailableError(DocumentIntelligenceError):
    code = "PARSER_UNAVAILABLE"
    retryable = True
    http_status = 503


class ParserTimeoutError(DocumentIntelligenceError):
    code = "PARSER_TIMEOUT"
    retryable = True
    http_status = 504


class ParserVersionMismatchError(DocumentIntelligenceError):
    code = "PARSER_VERSION_MISMATCH"
    severity = "P1"
    http_status = 503


class ParserDigestMismatchError(DocumentIntelligenceError):
    code = "PARSER_DIGEST_MISMATCH"
    severity = "P0"
    http_status = 503


class ParserOutputError(DocumentIntelligenceError):
    code = "OUTPUT_SCHEMA_INVALID"
    severity = "P0"
    http_status = 502


class EvidenceMissingError(DocumentIntelligenceError):
    code = "OUTPUT_EVIDENCE_MISSING"
    severity = "P0"
    http_status = 502


class RunStoreCorruptError(DocumentIntelligenceError):
    code = "RUN_STORE_CORRUPT"
    severity = "P0"
    http_status = 500


class StandardAccessDeniedError(DocumentIntelligenceError):
    code = "STANDARD_ACCESS_DENIED"
    severity = "P0"
    http_status = 403


class StandardWriteDisabledError(DocumentIntelligenceError):
    code = "STANDARD_WRITE_DISABLED"
    severity = "P0"
    http_status = 403


class StandardApprovalError(DocumentIntelligenceError):
    code = "STANDARD_APPROVAL_REQUIRED"
    severity = "P0"
    http_status = 409


class StandardMatchError(DocumentIntelligenceError):
    code = "STANDARD_MATCH_ERROR"
    severity = "P1"
    http_status = 422


class StandardStoreCorruptError(DocumentIntelligenceError):
    code = "STANDARD_STORE_CORRUPT"
    severity = "P0"
    http_status = 500


class MatchInputError(DocumentIntelligenceError):
    code = "MATCH_INPUT_INVALID"
    severity = "P1"
    http_status = 400


class StructureRecoveryError(DocumentIntelligenceError):
    code = "STRUCTURE_RECOVERY_ERROR"
    severity = "P1"
    http_status = 422


class StructureStoreCorruptError(DocumentIntelligenceError):
    code = "STRUCTURE_STORE_CORRUPT"
    severity = "P0"
    http_status = 500


class DomainPackError(DocumentIntelligenceError):
    code = "DOMAIN_PACK_ERROR"
    severity = "P1"
    http_status = 422


class DomainPackAccessDeniedError(DomainPackError):
    code = "DOMAIN_PACK_ACCESS_DENIED"
    severity = "P0"
    http_status = 403


class DomainPackWriteDisabledError(DomainPackError):
    code = "DOMAIN_PACK_WRITE_DISABLED"
    severity = "P0"
    http_status = 403


class DomainPackArchiveError(DomainPackError):
    code = "DOMAIN_PACK_ARCHIVE_INVALID"
    severity = "P0"
    http_status = 400


class DomainPackCompatibilityError(DomainPackError):
    code = "DOMAIN_PACK_INCOMPATIBLE"
    severity = "P0"
    http_status = 409


class DomainPackSignatureError(DomainPackError):
    code = "DOMAIN_PACK_SIGNATURE_INVALID"
    severity = "P0"
    http_status = 403


class DomainPackConflictError(DomainPackError):
    code = "DOMAIN_PACK_CONFLICT"
    severity = "P0"
    http_status = 409


class DomainPackStoreCorruptError(DomainPackError):
    code = "DOMAIN_PACK_STORE_CORRUPT"
    severity = "P0"
    http_status = 500


class DomainExecutionError(DomainPackError):
    code = "DOMAIN_EXECUTION_ERROR"
    severity = "P1"
    http_status = 422


class DomainResultStoreCorruptError(DomainPackError):
    code = "DOMAIN_RESULT_STORE_CORRUPT"
    severity = "P0"
    http_status = 500


class DomainReviewError(DomainPackError):
    code = "DOMAIN_REVIEW_INVALID"
    severity = "P1"
    http_status = 422


class FamilyDetectionError(DocumentIntelligenceError):
    code = "FAMILY_DETECTION_ERROR"
    severity = "P1"
    http_status = 422


class FamilyDetectionAccessDeniedError(FamilyDetectionError):
    code = "FAMILY_DETECTION_ACCESS_DENIED"
    severity = "P0"
    http_status = 403


class FamilyDetectionWriteDisabledError(FamilyDetectionError):
    code = "FAMILY_DETECTION_WRITE_DISABLED"
    severity = "P0"
    http_status = 403


class FamilyDetectionStoreCorruptError(FamilyDetectionError):
    code = "FAMILY_DETECTION_STORE_CORRUPT"
    severity = "P0"
    http_status = 500


class RillError(DocumentIntelligenceError):
    code = "RILL_ERROR"
    severity = "P1"
    http_status = 422


class RillUnavailableError(RillError):
    code = "RILL_RUNTIME_UNAVAILABLE"
    retryable = True
    http_status = 503


class RillProtocolError(RillError):
    code = "RILL_PROTOCOL_INVALID"
    severity = "P0"
    http_status = 502


class RillAccessDeniedError(RillError):
    code = "RILL_ACCESS_DENIED"
    severity = "P0"
    http_status = 403


class RillWriteDisabledError(RillError):
    code = "RILL_WRITE_DISABLED"
    severity = "P0"
    http_status = 403


class RillStoreCorruptError(RillError):
    code = "RILL_STORE_CORRUPT"
    severity = "P0"
    http_status = 500


class RillFeedbackError(RillError):
    code = "RILL_FEEDBACK_INVALID"
    severity = "P1"
    http_status = 409


class RillAssistError(RillError):
    code = "RILL_ASSIST_ERROR"
    severity = "P1"
    http_status = 422


class RillAssistAccessDeniedError(RillAssistError):
    code = "RILL_ASSIST_ACCESS_DENIED"
    severity = "P0"
    http_status = 403


class RillAssistDisabledError(RillAssistError):
    code = "RILL_ASSIST_DISABLED"
    severity = "P0"
    http_status = 403


class RillAssistQualificationError(RillAssistError):
    code = "RILL_ASSIST_NOT_QUALIFIED"
    severity = "P0"
    http_status = 409


class RillAssistExecutionError(RillAssistError):
    code = "RILL_ASSIST_EXECUTION_BLOCKED"
    severity = "P1"
    http_status = 409


class MLOpsError(DocumentIntelligenceError):
    code = "MLOPS_ERROR"
    severity = "P1"
    http_status = 422


class MLOpsAccessDeniedError(MLOpsError):
    code = "MLOPS_ACCESS_DENIED"
    severity = "P0"
    http_status = 403


class MLOpsWriteDisabledError(MLOpsError):
    code = "MLOPS_WRITE_DISABLED"
    severity = "P0"
    http_status = 403


class MLOpsReleaseDisabledError(MLOpsError):
    code = "MLOPS_RELEASE_DISABLED"
    severity = "P0"
    http_status = 403


class MLOpsGateError(MLOpsError):
    code = "MLOPS_GATE_BLOCKED"
    severity = "P0"
    http_status = 409


class ProductionQualificationError(DocumentIntelligenceError):
    code = "PRODUCTION_QUALIFICATION_ERROR"
    severity = "P1"
    http_status = 422


class ProductionQualificationAccessDeniedError(ProductionQualificationError):
    code = "PRODUCTION_QUALIFICATION_ACCESS_DENIED"
    severity = "P0"
    http_status = 403


class ProductionQualificationWriteDisabledError(ProductionQualificationError):
    code = "PRODUCTION_QUALIFICATION_WRITE_DISABLED"
    severity = "P0"
    http_status = 403


class ProductionQualificationGateError(ProductionQualificationError):
    code = "PRODUCTION_QUALIFICATION_BLOCKED"
    severity = "P0"
    http_status = 409


class ProductionStoreCorruptError(ProductionQualificationError):
    code = "PRODUCTION_QUALIFICATION_STORE_CORRUPT"
    severity = "P0"
    http_status = 500


class QualificationCampaignError(DocumentIntelligenceError):
    code = "QUALIFICATION_CAMPAIGN_ERROR"
    severity = "P1"
    http_status = 422


class QualificationCampaignAccessDeniedError(QualificationCampaignError):
    code = "QUALIFICATION_CAMPAIGN_ACCESS_DENIED"
    severity = "P0"
    http_status = 403


class QualificationCampaignWriteDisabledError(QualificationCampaignError):
    code = "QUALIFICATION_CAMPAIGN_WRITE_DISABLED"
    severity = "P0"
    http_status = 403


class QualificationCampaignGateError(QualificationCampaignError):
    code = "QUALIFICATION_CAMPAIGN_GATE_BLOCKED"
    severity = "P0"
    http_status = 409


class QualificationCampaignStoreCorruptError(QualificationCampaignError):
    code = "QUALIFICATION_CAMPAIGN_STORE_CORRUPT"
    severity = "P0"
    http_status = 500
