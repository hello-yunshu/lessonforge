from __future__ import annotations

import ast
import inspect
from importlib import resources
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel

from document_intelligence import __version__
from document_intelligence.config import Settings
from document_intelligence.domain_pack_sdk import (
    DOMAIN_PACK_FORMAT_VERSION,
    DocumentFamilyProfile,
    DomainOntology,
    DomainPackManifest,
    DomainPackTemplateKind,
    FamilyCue,
    LabelsFile,
    LoadedDomainPack,
    ObjectRule,
    RelationRule,
    ReviewConfig,
    RulesFile,
    ValidatorsFile,
    create_domain_pack_scaffold,
    load_domain_pack,
)
from document_intelligence.domain_runtime import DomainResult
from document_intelligence.family import FamilyDetectionResult
from document_intelligence.matching import MatchResult, StandardDocumentManifest
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
from document_intelligence.parser_sdk import DocumentParser, ParserRegistry
from document_intelligence.review import LabelUReviewExport, ReviewRecord
from document_intelligence.rill.assist_models import (
    BOUNDED_AUTO_ENABLED,
    AssistActivationRecord,
    AssistEvidenceAttestation,
    AssistExecutionRecord,
    AssistParserResumeRecord,
    AssistParserSuspensionRecord,
    AssistQualificationReport,
    AssistRevocationRecord,
)
from document_intelligence.rill.models import (
    ACTION_ARMS,
    RILL_FEATURE_SCHEMA_VERSION,
    RILL_SHADOW_SCHEMA_VERSION,
    RillObserveEvent,
    ShadowEvaluation,
    ShadowFeedbackRecord,
    ShadowSnapshotRecord,
)
from document_intelligence.rill.protocol import RILL_RUNTIME_API_VERSION_V3
from document_intelligence.schema import (
    SCHEMA_VERSION,
    ParsedDocument,
    ParserResult,
    ParseRun,
)
from document_intelligence.structure import StructureResult

from .models import ContractKind, FreezeManifest, FrozenContract, canonical_digest

FREEZE_BASELINE_PROJECT_VERSION = "1.0.0"
FROZEN_MANIFEST_V1_DIGEST = (
    "7b57ea9511ca142b24554f0146a76a9d58827d702dca0fa9686d7528981b7117"
)

FROZEN_API_OPERATIONS: tuple[tuple[str, str], ...] = (
    ("GET", "/healthz"),
    ("GET", "/v1/contracts/freeze"),
    ("GET", "/v1/domain-packs"),
    ("GET", "/v1/domain-packs/builtin"),
    ("GET", "/v1/domain-results/{domain_result_id}"),
    ("GET", "/v1/family-detections/{detection_id}"),
    ("GET", "/v1/mlops/inspect"),
    ("GET", "/v1/mlops/lineage/{candidate_id}"),
    ("GET", "/v1/parsers"),
    ("GET", "/v1/rill/assist/inspect"),
    ("GET", "/v1/rill/assist/qualifications/{report_id}"),
    ("GET", "/v1/rill/shadow/evaluations/{evaluation_id}"),
    ("GET", "/v1/rill/shadow/inspect"),
    ("GET", "/v1/rill/shadow/replay"),
    ("GET", "/v1/runs/{run_id}"),
    ("GET", "/v1/standard"),
    ("GET", "/v1/structures/{structure_id}"),
    ("POST", "/v1/domain-packs/{pack_id}/{version}/activate"),
    ("POST", "/v1/domain-packs/{pack_id}/deactivate"),
    ("POST", "/v1/domain-packs/builtin/{pack_id}/install"),
    ("POST", "/v1/domain-packs/install"),
    ("POST", "/v1/domain-results/{domain_result_id}/review/export"),
    ("POST", "/v1/domain-reviews"),
    ("POST", "/v1/domain/apply"),
    ("POST", "/v1/family/detect"),
    ("POST", "/v1/match"),
    ("POST", "/v1/mlops/active-learning/select"),
    ("POST", "/v1/mlops/approvals"),
    ("POST", "/v1/mlops/candidates"),
    ("POST", "/v1/mlops/datasets"),
    ("POST", "/v1/mlops/evaluations"),
    ("POST", "/v1/mlops/mlflow-runs"),
    ("POST", "/v1/mlops/promote/champion"),
    ("POST", "/v1/mlops/promote/shadow"),
    ("POST", "/v1/mlops/rollback"),
    ("POST", "/v1/mlops/shadow-validations"),
    ("POST", "/v1/parse"),
    ("POST", "/v1/rill/assist/activate"),
    ("POST", "/v1/rill/assist/attest"),
    ("POST", "/v1/rill/assist/execute"),
    ("POST", "/v1/rill/assist/parsers/resume"),
    ("POST", "/v1/rill/assist/parsers/suspend"),
    ("POST", "/v1/rill/assist/qualify"),
    ("POST", "/v1/rill/assist/revoke"),
    ("POST", "/v1/rill/shadow/evaluate"),
    ("POST", "/v1/rill/shadow/feedback"),
    ("POST", "/v1/rill/shadow/reset"),
    ("POST", "/v1/rill/shadow/snapshot"),
    ("POST", "/v1/standard/register"),
    ("POST", "/v1/structure/recover"),
    ("DELETE", "/v1/domain-packs/{pack_id}/{version}"),
)

PERMISSION_BOUNDARIES: tuple[tuple[str, str | None], ...] = (
    ("enable_standard_writes", "standard_access_token_sha256"),
    ("enable_domain_pack_writes", "domain_pack_access_token_sha256"),
    ("enable_family_detection_writes", "family_detection_access_token_sha256"),
    ("enable_rill_shadow_writes", "rill_access_token_sha256"),
    ("enable_rill_assist_writes", "rill_assist_access_token_sha256"),
    ("enable_rill_assist_execution", "rill_assist_access_token_sha256"),
    ("enable_mlops_writes", "mlops_access_token_sha256"),
    ("enable_mlops_release", "mlops_access_token_sha256"),
)

AUDIT_RECORDS: tuple[tuple[str, str, type[BaseModel], str], ...] = (
    ("standard", "standard-document", StandardDocumentManifest, "standard_id"),
    ("structures", "structure-result", StructureResult, "structure_id"),
    ("domain-results", "domain-result", DomainResult, "domain_result_id"),
    ("domain-reviews", "review-export", LabelUReviewExport, "export_id"),
    ("domain-reviews", "review-record", ReviewRecord, "review_id"),
    ("family-detections", "family-detection", FamilyDetectionResult, "detection_id"),
    ("rill-shadow", "shadow-evaluation", ShadowEvaluation, "evaluation_id"),
    ("rill-shadow", "shadow-feedback", ShadowFeedbackRecord, "feedback_id"),
    ("rill-shadow", "shadow-snapshot", ShadowSnapshotRecord, "snapshot_id"),
    ("rill-assist", "assist-attestation", AssistEvidenceAttestation, "attestation_id"),
    ("rill-assist", "assist-qualification", AssistQualificationReport, "report_id"),
    ("rill-assist", "assist-activation", AssistActivationRecord, "activation_id"),
    ("rill-assist", "assist-execution", AssistExecutionRecord, "execution_id"),
    ("rill-assist", "assist-revocation", AssistRevocationRecord, "revocation_id"),
    ("rill-assist", "parser-suspension", AssistParserSuspensionRecord, "suspension_id"),
    ("rill-assist", "parser-resume", AssistParserResumeRecord, "resume_id"),
    ("mlops", "active-learning-batch", ActiveLearningBatch, "batch_id"),
    ("mlops", "dataset-snapshot", DatasetSnapshot, "snapshot_id"),
    ("mlops", "mlflow-run", MLflowRunRecord, "run_id"),
    ("mlops", "model-candidate", ModelCandidate, "candidate_id"),
    ("mlops", "candidate-evaluation", CandidateEvaluationReport, "report_id"),
    ("mlops", "shadow-validation", ShadowValidationReport, "report_id"),
    ("mlops", "release-approval", ReleaseApproval, "approval_id"),
    ("mlops", "alias-update", AliasUpdateRecord, "update_id"),
    ("mlops", "rollback", RollbackRecord, "rollback_id"),
)

ROLLBACK_GUARANTEES: tuple[str, ...] = (
    "assist activation can be revoked without deleting its audit record",
    "parser suspension is reversible and native-pdf cannot be suspended",
    "candidate promotion preserves previous Champion as Rollback",
    "Champion promotion requires offline evaluation, Shadow evidence, and approval",
    "rollback changes aliases atomically and never rewrites model artifacts",
    "runtime failure falls back to deterministic non-Rill behavior",
)

PRODUCTION_BLOCKERS: tuple[str, ...] = (
    "external parser artifacts are not production-qualified in this repository",
    "formal Ruff and Mypy CI evidence is not embedded in the offline package",
    "PyMuPDF production distribution licensing remains unresolved",
    "real multi-domain gold and challenge datasets are not embedded",
    "scale, concurrency, and long-duration soak evidence is not embedded",
)


def _schema_payload(models: Iterable[type[BaseModel]]) -> dict[str, Any]:
    return {
        model.__name__: model.model_json_schema()
        for model in sorted(models, key=lambda item: item.__name__)
    }


def _signature(value: Any) -> str:
    return str(inspect.signature(value))


def _public_class_surface(cls: type[Any]) -> dict[str, str]:
    return {
        name: _signature(member)
        for name, member in inspect.getmembers(cls)
        if not name.startswith("_") and callable(member)
    }


def _contract(contract_id: str, kind: ContractKind, payload: dict[str, Any]) -> FrozenContract:
    return FrozenContract(
        contract_id=contract_id,
        kind=kind,
        contract_version="1",
        digest=canonical_digest(payload),
        payload=payload,
    )


def current_contracts() -> list[FrozenContract]:
    settings = Settings()
    permission_defaults = {
        flag: getattr(settings, flag) for flag, _ in PERMISSION_BOUNDARIES
    }
    contracts = [
        _contract(
            "audit-log-v1",
            ContractKind.AUDIT_LOG_FORMAT,
            {
                "immutable": True,
                "canonical_json": "utf-8, sorted keys, compact separators",
                "records": [
                    {
                        "namespace": namespace,
                        "record_type": record_type,
                        "id_field": id_field,
                        "schema": model.model_json_schema(),
                    }
                    for namespace, record_type, model, id_field in AUDIT_RECORDS
                ],
            },
        ),
        _contract(
            "core-schema-v1",
            ContractKind.CORE_SCHEMA,
            {
                "schema_version": SCHEMA_VERSION,
                "models": _schema_payload((ParsedDocument, ParserResult, ParseRun)),
            },
        ),
        _contract(
            "domain-pack-sdk-v1",
            ContractKind.DOMAIN_PACK_SDK,
            {
                "format_version": DOMAIN_PACK_FORMAT_VERSION,
                "exports": sorted(
                    (
                        "DOMAIN_PACK_FORMAT_VERSION",
                        "DocumentFamilyProfile",
                        "DomainOntology",
                        "DomainPackManifest",
                        "DomainPackTemplateKind",
                        "FamilyCue",
                        "LabelsFile",
                        "LoadedDomainPack",
                        "ObjectRule",
                        "RelationRule",
                        "ReviewConfig",
                        "RulesFile",
                        "ValidatorsFile",
                        "create_domain_pack_scaffold",
                        "load_domain_pack",
                    )
                ),
                "models": _schema_payload(
                    (
                        DocumentFamilyProfile,
                        DomainOntology,
                        DomainPackManifest,
                        FamilyCue,
                        LabelsFile,
                        LoadedDomainPack,
                        ObjectRule,
                        RelationRule,
                        ReviewConfig,
                        RulesFile,
                        ValidatorsFile,
                    )
                ),
                "template_kinds": [item.value for item in DomainPackTemplateKind],
                "callables": {
                    "create_domain_pack_scaffold": _signature(
                        create_domain_pack_scaffold
                    ),
                    "load_domain_pack": _signature(load_domain_pack),
                },
            },
        ),
        _contract(
            "parser-sdk-v1",
            ContractKind.PARSER_SDK,
            {
                "exports": ["DocumentParser", "ParserRegistry"],
                "document_parser": _public_class_surface(DocumentParser),
                "parser_registry": _public_class_surface(ParserRegistry),
            },
        ),
        _contract(
            "permission-boundary-v1",
            ContractKind.PERMISSION_BOUNDARY,
            {
                "default_closed": permission_defaults,
                "token_bindings": [list(item) for item in PERMISSION_BOUNDARIES],
                "bounded_auto": BOUNDED_AUTO_ENABLED,
                "family_detection_advisory_only": True,
                "domain_pack_arbitrary_code": False,
            },
        ),
        _contract(
            "release-gates-v1",
            ContractKind.RELEASE_GATES,
            {
                "required_phase_verifiers": [
                    f"scripts/verify_phase{number}.py" for number in range(1, 10)
                ],
                "required_checks": [
                    "all phase compatibility gates",
                    "all tests",
                    "branch coverage >= 80 percent",
                    "static sanity",
                    "wheel build and isolated import",
                    "source manifest verification",
                    "independent ZIP extraction verification",
                ],
                "production_state_must_be_empty": True,
                "production_qualification_separate_from_engineering_freeze": True,
            },
        ),
        _contract(
            "rest-api-v1",
            ContractKind.REST_API,
            {"operations": [list(item) for item in FROZEN_API_OPERATIONS]},
        ),
        _contract(
            "rill-event-protocol-v1",
            ContractKind.RILL_PROTOCOL,
            {
                "runtime_api_version": RILL_RUNTIME_API_VERSION_V3,
                "shadow_schema_version": RILL_SHADOW_SCHEMA_VERSION,
                "feature_schema_version": RILL_FEATURE_SCHEMA_VERSION,
                "action_arms": list(ACTION_ARMS),
                "models": _schema_payload(
                    (
                        RillObserveEvent,
                        ShadowEvaluation,
                        ShadowFeedbackRecord,
                        ShadowSnapshotRecord,
                        AssistEvidenceAttestation,
                        AssistQualificationReport,
                        AssistActivationRecord,
                        AssistExecutionRecord,
                        AssistRevocationRecord,
                    )
                ),
                "shadow_only_without_qualification": True,
                "bounded_auto": BOUNDED_AUTO_ENABLED,
            },
        ),
        _contract(
            "rollback-behavior-v1",
            ContractKind.ROLLBACK_BEHAVIOR,
            {"guarantees": list(ROLLBACK_GUARANTEES)},
        ),
        _contract(
            "version-semantics-v1",
            ContractKind.VERSION_SEMANTICS,
            {
                "baseline_version": FREEZE_BASELINE_PROJECT_VERSION,
                "stable_major": 1,
                "patch": "no frozen contract changes",
                "minor": "new isolated capability; existing frozen contracts unchanged",
                "major": "incompatible contract changes require migration and major plan",
                "persisted_legacy_schema_versions_remain_readable": True,
                "domain_pack_engine_range": ">=0.4,<2.0",
            },
        ),
    ]
    return sorted(contracts, key=lambda item: item.contract_id)


def build_manifest() -> FreezeManifest:
    contracts = current_contracts()
    payload: dict[str, Any] = {
        "format_version": 1,
        "schema_version": "1.0",
        "freeze_id": "freeze-1-0-0",
        "project": "document-intelligence",
        "project_version": FREEZE_BASELINE_PROJECT_VERSION,
        "stable_major": 1,
        "status": "engineering_frozen",
        "production_qualified": False,
        "contracts": [item.model_dump(mode="json") for item in contracts],
        "production_blockers": sorted(PRODUCTION_BLOCKERS),
    }
    return FreezeManifest(**payload, manifest_digest=canonical_digest(payload))


def default_manifest_path() -> Path:
    return Path(resources.files("document_intelligence.defaults")) / "frozen_contracts_v1.json"


def discover_api_operations() -> set[tuple[str, str]]:
    source_path = Path(__file__).resolve().parents[1] / "api" / "main.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    operations: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            function = decorator.func
            if not (
                isinstance(function, ast.Attribute)
                and isinstance(function.value, ast.Name)
                and function.value.id == "app"
                and function.attr in {"get", "post", "put", "patch", "delete"}
            ):
                continue
            path_node = decorator.args[0]
            if isinstance(path_node, ast.Constant) and isinstance(path_node.value, str):
                path = path_node.value
                if path == "/healthz" or path.startswith("/v1/"):
                    operations.add((function.attr.upper(), path))
    return operations
