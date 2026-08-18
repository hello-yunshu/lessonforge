from __future__ import annotations

import argparse
import json
from pathlib import Path

from document_intelligence.config import Settings
from document_intelligence.domain_pack_sdk import (
    DomainPackTemplateKind,
    create_domain_pack_scaffold,
)
from document_intelligence.exceptions import (
    DomainPackWriteDisabledError,
    FamilyDetectionWriteDisabledError,
    RillAssistDisabledError,
    RillWriteDisabledError,
    MLOpsReleaseDisabledError,
    MLOpsWriteDisabledError,
    StandardWriteDisabledError,
    ProductionQualificationWriteDisabledError,
    QualificationCampaignWriteDisabledError,
)
from document_intelligence.freeze import FreezeService
from document_intelligence.mlops.models import (
    ApprovalRequest,
    CandidateRegistrationRequest,
    DatasetSnapshotRequest,
    EvaluationRequest,
    MLflowRunRequest,
    PromoteRequest,
    RollbackRequest,
    ShadowValidationRequest,
)
from document_intelligence.matching import StandardLibrary, StandardMatcher
from document_intelligence.production import (
    DatasetQualificationRequest,
    LicenseQualificationRequest,
    ParserQualificationRequest,
    PilotQualificationRequest,
    ProductionQualificationRequest,
    ScaleQualificationRequest,
    SupplyChainQualificationRequest,
)
from document_intelligence.review import LabelUReviewSubmission
from document_intelligence.rill import (
    AssistActivationRequest,
    AssistAttestationRequest,
    AssistExecutionRequest,
    AssistQualificationRequest,
    AssistRevocationRequest,
    AssistParserSuspensionRequest,
    AssistParserResumeRequest,
    ShadowFeedbackInput,
)
from document_intelligence.services import (
    IngestionPolicy,
    build_document_family_service,
    build_domain_pack_registry,
    build_domain_review_service,
    build_domain_runtime_service,
    build_orchestrator,
    build_rill_assist_service,
    build_rill_shadow_service,
    build_mlops_service,
    build_production_qualification_service,
    build_qualification_campaign_service,
    build_structure_service,
    ingest_bytes,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="doc-intelligence")
    sub = parser.add_subparsers(dest="command", required=True)

    parse = sub.add_parser("parse", help="parse a local PDF/image")
    parse.add_argument("file", type=Path)
    parse.add_argument("--parser", default="auto")
    parse.add_argument("--domain-pack", default=None)
    parse.add_argument("--output", type=Path, default=None)

    freeze_inspect = sub.add_parser(
        "freeze-inspect", help="show the immutable 1.0 contract manifest"
    )
    freeze_inspect.add_argument("--output", type=Path, default=None)
    freeze_verify = sub.add_parser(
        "freeze-verify", help="verify live contracts against the 1.0 freeze"
    )
    freeze_verify.add_argument("--output", type=Path, default=None)

    sub.add_parser("parsers", help="show parser health")
    sub.add_parser("standard-list", help="list approved standard documents")

    register = sub.add_parser("standard-register", help="approve and register an existing run")
    register.add_argument("run_id")
    register.add_argument("--reviewer", required=True)
    register.add_argument("--note", required=True)
    register.add_argument("--approved", action="store_true")

    match = sub.add_parser("match", help="match an image/PDF page against the standard library")
    match.add_argument("file", type=Path)
    match.add_argument("--page-index", type=int, default=0)
    match.add_argument("--query-text", default=None)
    match.add_argument("--top-k", type=int, default=5)
    match.add_argument("--include-standard", action="store_true")
    match.add_argument("--output", type=Path, default=None)

    structure = sub.add_parser("structure-recover", help="recover generic structure")
    structure.add_argument("run_id")
    structure.add_argument("--output", type=Path, default=None)

    structure_get = sub.add_parser("structure-get", help="read a structure result")
    structure_get.add_argument("structure_id")
    structure_get.add_argument("--output", type=Path, default=None)

    pack_install = sub.add_parser("domain-pack-install", help="install a Domain Pack")
    pack_install.add_argument("path", type=Path)
    pack_install.add_argument("--activate", action="store_true")

    sub.add_parser("domain-pack-builtin-list", help="list packaged built-in Domain Packs")

    builtin_install = sub.add_parser(
        "domain-pack-install-builtin", help="install a packaged built-in Domain Pack"
    )
    builtin_install.add_argument("pack_id")
    builtin_install.add_argument("--activate", action="store_true")

    scaffold = sub.add_parser("domain-pack-scaffold", help="create a declarative Domain Pack")
    scaffold.add_argument("target_parent", type=Path)
    scaffold.add_argument("--id", required=True, dest="pack_id")
    scaffold.add_argument("--version", default="0.1.0")
    scaffold.add_argument(
        "--template",
        choices=[item.value for item in DomainPackTemplateKind],
        default=DomainPackTemplateKind.CLASSIFICATION.value,
    )
    scaffold.add_argument("--without-family-profile", action="store_true")

    sub.add_parser("domain-pack-list", help="list installed Domain Packs")

    pack_activate = sub.add_parser("domain-pack-activate", help="activate a Domain Pack")
    pack_activate.add_argument("pack_id")
    pack_activate.add_argument("version")

    pack_deactivate = sub.add_parser("domain-pack-deactivate", help="deactivate a Domain Pack")
    pack_deactivate.add_argument("pack_id")

    pack_uninstall = sub.add_parser("domain-pack-uninstall", help="uninstall a Domain Pack")
    pack_uninstall.add_argument("pack_id")
    pack_uninstall.add_argument("version")

    family_detect = sub.add_parser(
        "family-detect", help="record an advisory document-family detection"
    )
    family_detect.add_argument("structure_id")
    family_detect.add_argument("--output", type=Path, default=None)

    family_get = sub.add_parser("family-get", help="read a family detection record")
    family_get.add_argument("detection_id")
    family_get.add_argument("--output", type=Path, default=None)

    domain_apply = sub.add_parser("domain-apply", help="apply a Domain Pack to a structure")
    domain_apply.add_argument("structure_id")
    domain_apply.add_argument("pack_id")
    domain_apply.add_argument("--version", default=None)
    domain_apply.add_argument("--no-fallback", action="store_true")
    domain_apply.add_argument("--output", type=Path, default=None)

    domain_get = sub.add_parser("domain-get", help="read a committed domain result")
    domain_get.add_argument("domain_result_id")
    domain_get.add_argument("--output", type=Path, default=None)

    review_export = sub.add_parser("domain-review-export", help="export LabelU review JSON")
    review_export.add_argument("domain_result_id")
    review_export.add_argument("--output", type=Path, required=True)

    review_submit = sub.add_parser("domain-review-submit", help="submit LabelU review JSON")
    review_submit.add_argument("file", type=Path)
    review_submit.add_argument("--output", type=Path, default=None)

    rill_evaluate = sub.add_parser("rill-shadow-evaluate", help="record a Rill Shadow suggestion")
    rill_evaluate.add_argument("parse_run_id")
    rill_evaluate.add_argument("--structure-id", default=None)
    rill_evaluate.add_argument("--domain-result-id", default=None)
    rill_evaluate.add_argument("--output", type=Path, default=None)

    rill_get = sub.add_parser("rill-shadow-get", help="read a Rill Shadow evaluation")
    rill_get.add_argument("evaluation_id")
    rill_get.add_argument("--output", type=Path, default=None)

    rill_feedback = sub.add_parser(
        "rill-shadow-feedback", help="submit delayed Shadow feedback JSON"
    )
    rill_feedback.add_argument("file", type=Path)
    rill_feedback.add_argument("--output", type=Path, default=None)

    sub.add_parser("rill-shadow-inspect", help="inspect Rill Shadow without actions")
    sub.add_parser("rill-shadow-replay", help="calculate offline Shadow replay metrics")
    sub.add_parser("rill-shadow-snapshot", help="persist Rill and drift state")
    sub.add_parser("rill-shadow-reset", help="snapshot then reset Shadow state")

    assist_attest = sub.add_parser("rill-assist-attest", help="submit expert evidence JSON")
    assist_attest.add_argument("file", type=Path)
    assist_attest.add_argument("--output", type=Path, default=None)

    assist_qualify = sub.add_parser("rill-assist-qualify", help="create qualification report")
    assist_qualify.add_argument("file", type=Path)
    assist_qualify.add_argument("--output", type=Path, default=None)

    assist_get = sub.add_parser("rill-assist-qualification-get", help="read qualification")
    assist_get.add_argument("report_id")
    assist_get.add_argument("--output", type=Path, default=None)

    assist_activate = sub.add_parser(
        "rill-assist-activate", help="activate qualified Tier-1 actions"
    )
    assist_activate.add_argument("file", type=Path)
    assist_activate.add_argument("--output", type=Path, default=None)

    assist_revoke = sub.add_parser("rill-assist-revoke", help="revoke an Assist activation")
    assist_revoke.add_argument("file", type=Path)
    assist_revoke.add_argument("--output", type=Path, default=None)

    assist_suspend = sub.add_parser(
        "rill-assist-parser-suspend",
        help="temporarily suspend an abnormal non-native parser",
    )
    assist_suspend.add_argument("file", type=Path)
    assist_suspend.add_argument("--output", type=Path, default=None)

    assist_resume = sub.add_parser(
        "rill-assist-parser-resume",
        help="resume a temporarily suspended parser",
    )
    assist_resume.add_argument("file", type=Path)
    assist_resume.add_argument("--output", type=Path, default=None)

    assist_execute = sub.add_parser(
        "rill-assist-execute", help="execute one qualified additive action"
    )
    assist_execute.add_argument("activation_id")
    assist_execute.add_argument("evaluation_id")
    assist_execute.add_argument("--output", type=Path, default=None)

    sub.add_parser("rill-assist-inspect", help="inspect Assist without changing state")

    active = sub.add_parser("mlops-active-select", help="select an active-learning batch")
    active.add_argument("--max-items", type=int, default=100)
    active.add_argument("--max-per-family", type=int, default=20)
    active.add_argument("--output", type=Path, default=None)
    for command, help_text in (
        ("mlops-dataset-create", "register a DVC-backed dataset snapshot"),
        ("mlops-mlflow-record", "register an MLflow run attestation"),
        ("mlops-candidate-register", "register a model candidate"),
        ("mlops-evaluate", "record gold and challenge evaluation"),
        ("mlops-shadow-validate", "record immutable Shadow evidence"),
        ("mlops-approve", "record human release approval"),
        ("mlops-promote-shadow", "promote an approved candidate to Shadow"),
        ("mlops-promote-champion", "promote a Shadow candidate to Champion"),
        ("mlops-rollback", "rollback Champion to the retained predecessor"),
    ):
        item = sub.add_parser(command, help=help_text)
        item.add_argument("file", type=Path)
        item.add_argument("--output", type=Path, default=None)
    lineage = sub.add_parser("mlops-lineage", help="show complete candidate lineage")
    lineage.add_argument("candidate_id")
    lineage.add_argument("--output", type=Path, default=None)
    sub.add_parser("mlops-inspect", help="inspect MLOps lineage and aliases")
    for command, help_text in (
        ("production-dataset-record", "record real gold or challenge evidence"),
        ("production-parser-record", "record fixed-artifact parser qualification"),
        ("production-scale-record", "record scale, soak, and recovery evidence"),
        ("production-supply-chain-record", "record CI and supply-chain evidence"),
        ("production-license-record", "record license resolution evidence"),
        ("production-pilot-record", "record real pilot evidence"),
        ("production-qualify", "evaluate all production qualification gates"),
    ):
        item = sub.add_parser(command, help=help_text)
        item.add_argument("file", type=Path)
        item.add_argument("--output", type=Path, default=None)
    production_get = sub.add_parser("production-report-get", help="read a qualification report")
    production_get.add_argument("report_id")
    production_get.add_argument("--output", type=Path, default=None)
    sub.add_parser("production-inspect", help="inspect production qualification evidence")
    for command, help_text in (
        ("campaign-create", "create an immutable qualification campaign"),
        ("campaign-start", "start a qualification campaign"),
        ("campaign-pause", "pause a qualification campaign"),
        ("campaign-resume", "resume a qualification campaign"),
        ("campaign-cancel", "cancel a qualification campaign"),
        ("campaign-step-claim", "claim a ready campaign step"),
        ("campaign-step-link", "link verified production evidence"),
        ("campaign-step-complete", "complete a leased step"),
        ("campaign-finalize", "evaluate linked production evidence"),
    ):
        item = sub.add_parser(command, help=help_text)
        if command != "campaign-create":
            item.add_argument("campaign_id")
        if command.startswith("campaign-step-"):
            item.add_argument("step_id")
        item.add_argument("file", type=Path)
        item.add_argument("--output", type=Path, default=None)
    campaign_get = sub.add_parser("campaign-get", help="read a qualification campaign")
    campaign_get.add_argument("campaign_id")
    campaign_get.add_argument("--output", type=Path, default=None)
    campaign_export = sub.add_parser(
        "campaign-bundle-export", help="export a sealed campaign bundle"
    )
    campaign_export.add_argument("campaign_id")
    campaign_export.add_argument("output", type=Path)
    campaign_verify = sub.add_parser(
        "campaign-bundle-verify", help="verify a sealed campaign bundle"
    )
    campaign_verify.add_argument("file", type=Path)
    campaign_verify.add_argument("--output", type=Path, default=None)
    campaign_import = sub.add_parser(
        "campaign-bundle-import", help="restore a sealed campaign bundle"
    )
    campaign_import.add_argument("file", type=Path)
    campaign_import.add_argument("--output", type=Path, default=None)
    sub.add_parser("campaign-inspect", help="inspect qualification campaigns")
    return parser


def _emit(payload: object, output: Path | None = None) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


def _require_domain_writes(settings: Settings) -> None:
    if not settings.enable_domain_pack_writes:
        raise DomainPackWriteDisabledError(
            "domain-pack writes are disabled; set DI_ENABLE_DOMAIN_PACK_WRITES=true "
            "only in an approved environment"
        )


def _require_family_writes(settings: Settings) -> None:
    if not settings.enable_family_detection_writes:
        raise FamilyDetectionWriteDisabledError(
            "family-detection writes are disabled; set DI_ENABLE_FAMILY_DETECTION_WRITES=true "
            "only in an approved environment"
        )


def _require_rill_writes(settings: Settings) -> None:
    if not settings.enable_rill_shadow_writes:
        raise RillWriteDisabledError(
            "Rill Shadow writes are disabled; set DI_ENABLE_RILL_SHADOW_WRITES=true "
            "only in an approved Shadow environment"
        )


def _require_assist_writes(settings: Settings) -> None:
    if not settings.enable_rill_assist_writes:
        raise RillAssistDisabledError(
            "Rill Assist writes are disabled; qualification governance is closed"
        )


def _require_assist_execution(settings: Settings) -> None:
    if not settings.enable_rill_assist_execution:
        raise RillAssistDisabledError(
            "Rill Assist execution is disabled; boundedAuto remains hard-disabled"
        )


def _require_mlops_writes(settings: Settings) -> None:
    if not settings.enable_mlops_writes:
        raise MLOpsWriteDisabledError(
            "MLOps writes are disabled; set DI_ENABLE_MLOPS_WRITES=true only in governance"
        )


def _require_mlops_release(settings: Settings) -> None:
    if not settings.enable_mlops_release:
        raise MLOpsReleaseDisabledError(
            "MLOps release is disabled; registration alone cannot change deployment aliases"
        )


def _require_production_writes(settings: Settings) -> None:
    if not settings.enable_production_qualification_writes:
        raise ProductionQualificationWriteDisabledError(
            "production qualification writes are disabled; evidence registration is closed"
        )

def _require_campaign_writes(settings: Settings) -> None:
    if not settings.enable_qualification_campaign_writes:
        raise QualificationCampaignWriteDisabledError(
            "qualification campaign writes are disabled"
        )


def main() -> int:
    args = build_parser().parse_args()
    settings = Settings.from_env()
    if args.command in {"freeze-inspect", "freeze-verify"}:
        service = FreezeService()
        payload = (
            service.load_manifest().model_dump(mode="json")
            if args.command == "freeze-inspect"
            else service.verify().model_dump(mode="json")
        )
        _emit(payload, args.output)
        if args.command == "freeze-verify" and not payload["compatible"]:
            return 1
        return 0
    orchestrator = build_orchestrator(settings)
    structure_service = build_structure_service(settings, artifact_store=orchestrator.store)
    domain_registry = build_domain_pack_registry(settings)
    domain_service = build_domain_runtime_service(
        settings,
        artifact_store=orchestrator.store,
        structure_service=structure_service,
        domain_registry=domain_registry,
    )
    family_service = build_document_family_service(
        settings,
        artifact_store=orchestrator.store,
        structure_service=structure_service,
        domain_registry=domain_registry,
    )
    review_service = build_domain_review_service(
        settings,
        artifact_store=orchestrator.store,
        structure_service=structure_service,
        domain_service=domain_service,
    )
    rill_service = build_rill_shadow_service(
        settings,
        artifact_store=orchestrator.store,
        structure_service=structure_service,
        domain_service=domain_service,
    )
    assist_service = build_rill_assist_service(
        settings,
        orchestrator=orchestrator,
        shadow_service=rill_service,
        artifact_store=orchestrator.store,
        structure_service=structure_service,
        domain_service=domain_service,
    )
    mlops_service = build_mlops_service(
        settings,
        orchestrator=orchestrator,
        shadow_service=rill_service,
        assist_service=assist_service,
        artifact_store=orchestrator.store,
        structure_service=structure_service,
        domain_service=domain_service,
    )
    production_service = build_production_qualification_service(settings)
    campaign_service = build_qualification_campaign_service(
        settings, production_service=production_service
    )
    library = StandardLibrary(orchestrator.store, max_render_pixels=settings.max_render_pixels)
    matcher = StandardMatcher(
        library,
        high_threshold=settings.match_high_threshold,
        local_threshold=settings.match_local_threshold,
        min_margin=settings.match_min_margin,
        min_local_inliers=settings.match_min_local_inliers,
        max_pdf_pages=settings.max_pdf_pages,
        max_render_pixels=settings.max_render_pixels,
    )
    try:
        if args.command == "campaign-create":
            _require_campaign_writes(settings)
            payload = CampaignCreateRequest.model_validate_json(
                args.file.read_text(encoding="utf-8")
            )
            _emit(campaign_service.create(payload).model_dump(mode="json"), args.output)
            return 0
        actor_commands = {
            "campaign-start": campaign_service.start,
            "campaign-pause": campaign_service.pause,
            "campaign-resume": campaign_service.resume,
            "campaign-cancel": campaign_service.cancel,
        }
        if args.command in actor_commands:
            _require_campaign_writes(settings)
            payload = CampaignActorRequest.model_validate_json(
                args.file.read_text(encoding="utf-8")
            )
            _emit(
                actor_commands[args.command](args.campaign_id, payload).model_dump(
                    mode="json"
                ),
                args.output,
            )
            return 0
        if args.command == "campaign-step-claim":
            _require_campaign_writes(settings)
            payload = StepClaimRequest.model_validate_json(args.file.read_text(encoding="utf-8"))
            _emit(
                campaign_service.claim(
                    args.campaign_id, args.step_id, payload
                ).model_dump(mode="json"),
                args.output,
            )
            return 0
        if args.command == "campaign-step-link":
            _require_campaign_writes(settings)
            payload = EvidenceLinkRequest.model_validate_json(args.file.read_text(encoding="utf-8"))
            _emit(
                campaign_service.link_evidence(
                    args.campaign_id, args.step_id, payload
                ).model_dump(mode="json"),
                args.output,
            )
            return 0
        if args.command == "campaign-step-complete":
            _require_campaign_writes(settings)
            payload = StepTransitionRequest.model_validate_json(
                args.file.read_text(encoding="utf-8")
            )
            _emit(
                campaign_service.complete_step(
                    args.campaign_id, args.step_id, payload
                ).model_dump(mode="json"),
                args.output,
            )
            return 0
        if args.command == "campaign-finalize":
            _require_campaign_writes(settings)
            payload = CampaignFinalizeRequest.model_validate_json(
                args.file.read_text(encoding="utf-8")
            )
            _emit(
                campaign_service.finalize(args.campaign_id, payload).model_dump(
                    mode="json"
                ),
                args.output,
            )
            return 0
        if args.command == "campaign-get":
            _emit(campaign_service.snapshot(args.campaign_id).model_dump(mode="json"), args.output)
            return 0
        if args.command == "campaign-bundle-export":
            _require_campaign_writes(settings)
            _emit(campaign_service.export_bundle(args.campaign_id, args.output))
            return 0
        if args.command == "campaign-bundle-verify":
            _emit(campaign_service.verify_bundle(args.file), args.output)
            return 0
        if args.command == "campaign-bundle-import":
            _require_campaign_writes(settings)
            _require_production_writes(settings)
            _emit(
                campaign_service.import_bundle(args.file).model_dump(mode="json"),
                args.output,
            )
            return 0
        if args.command == "campaign-inspect":
            _emit(campaign_service.inspect())
            return 0
        production_requests = {
            "production-dataset-record": (
                DatasetQualificationRequest, production_service.record_dataset
            ),
            "production-parser-record": (
                ParserQualificationRequest, production_service.record_parser
            ),
            "production-scale-record": (
                ScaleQualificationRequest, production_service.record_scale
            ),
            "production-supply-chain-record": (
                SupplyChainQualificationRequest, production_service.record_supply_chain
            ),
            "production-license-record": (
                LicenseQualificationRequest, production_service.record_license
            ),
            "production-pilot-record": (
                PilotQualificationRequest, production_service.record_pilot
            ),
            "production-qualify": (
                ProductionQualificationRequest, production_service.qualify
            ),
        }
        if args.command in production_requests:
            _require_production_writes(settings)
            model, operation = production_requests[args.command]
            payload = model.model_validate_json(args.file.read_text(encoding="utf-8"))
            _emit(operation(payload).model_dump(mode="json"), args.output)
            return 0
        if args.command == "production-report-get":
            _emit(
                production_service.store.read_report(args.report_id).model_dump(mode="json"),
                args.output,
            )
            return 0
        if args.command == "production-inspect":
            _emit(production_service.inspect())
            return 0
        if args.command == "mlops-active-select":
            _require_mlops_writes(settings)
            _emit(
                mlops_service.select_active_learning(
                    max_items=args.max_items, max_per_family=args.max_per_family
                ).model_dump(mode="json"),
                args.output,
            )
            return 0
        mlops_requests = {
            "mlops-dataset-create": (DatasetSnapshotRequest, mlops_service.create_snapshot),
            "mlops-mlflow-record": (MLflowRunRequest, mlops_service.record_mlflow_run),
            "mlops-candidate-register": (
                CandidateRegistrationRequest, mlops_service.register_candidate
            ),
            "mlops-evaluate": (EvaluationRequest, mlops_service.evaluate),
            "mlops-shadow-validate": (
                ShadowValidationRequest, mlops_service.record_shadow_validation
            ),
            "mlops-approve": (ApprovalRequest, mlops_service.approve),
        }
        if args.command in mlops_requests:
            _require_mlops_writes(settings)
            model, operation = mlops_requests[args.command]
            payload = model.model_validate_json(args.file.read_text(encoding="utf-8"))
            _emit(operation(payload).model_dump(mode="json"), args.output)
            return 0
        if args.command in {"mlops-promote-shadow", "mlops-promote-champion"}:
            _require_mlops_writes(settings)
            _require_mlops_release(settings)
            payload = PromoteRequest.model_validate_json(args.file.read_text(encoding="utf-8"))
            operation = (
                mlops_service.promote_to_shadow
                if args.command == "mlops-promote-shadow"
                else mlops_service.promote_to_champion
            )
            _emit(operation(payload).model_dump(mode="json"), args.output)
            return 0
        if args.command == "mlops-rollback":
            _require_mlops_writes(settings)
            _require_mlops_release(settings)
            payload = RollbackRequest.model_validate_json(args.file.read_text(encoding="utf-8"))
            _emit(mlops_service.rollback(payload).model_dump(mode="json"), args.output)
            return 0
        if args.command == "mlops-lineage":
            _emit(mlops_service.lineage(args.candidate_id), args.output)
            return 0
        if args.command == "mlops-inspect":
            _emit(mlops_service.inspect())
            return 0
        if args.command == "rill-assist-attest":
            _require_assist_writes(settings)
            payload = AssistAttestationRequest.model_validate_json(
                args.file.read_text(encoding="utf-8")
            )
            _emit(assist_service.create_attestation(payload).model_dump(mode="json"), args.output)
            return 0
        if args.command == "rill-assist-qualify":
            _require_assist_writes(settings)
            payload = AssistQualificationRequest.model_validate_json(
                args.file.read_text(encoding="utf-8")
            )
            _emit(
                assist_service.qualify(payload.requested_actions).model_dump(mode="json"),
                args.output,
            )
            return 0
        if args.command == "rill-assist-qualification-get":
            _emit(
                assist_service.store.read_qualification(args.report_id).model_dump(
                    mode="json"
                ),
                args.output,
            )
            return 0
        if args.command == "rill-assist-activate":
            _require_assist_writes(settings)
            payload = AssistActivationRequest.model_validate_json(
                args.file.read_text(encoding="utf-8")
            )
            _emit(assist_service.activate(payload).model_dump(mode="json"), args.output)
            return 0
        if args.command == "rill-assist-revoke":
            _require_assist_writes(settings)
            payload = AssistRevocationRequest.model_validate_json(
                args.file.read_text(encoding="utf-8")
            )
            _emit(assist_service.revoke(payload).model_dump(mode="json"), args.output)
            return 0
        if args.command == "rill-assist-parser-suspend":
            _require_assist_writes(settings)
            _require_assist_execution(settings)
            payload = AssistParserSuspensionRequest.model_validate_json(
                args.file.read_text(encoding="utf-8")
            )
            _emit(assist_service.suspend_parser(payload).model_dump(mode="json"), args.output)
            return 0
        if args.command == "rill-assist-parser-resume":
            _require_assist_writes(settings)
            _require_assist_execution(settings)
            payload = AssistParserResumeRequest.model_validate_json(
                args.file.read_text(encoding="utf-8")
            )
            _emit(assist_service.resume_parser(payload).model_dump(mode="json"), args.output)
            return 0
        if args.command == "rill-assist-execute":
            _require_assist_writes(settings)
            _require_assist_execution(settings)
            request = AssistExecutionRequest(
                activation_id=args.activation_id, evaluation_id=args.evaluation_id
            )
            _emit(
                assist_service.execute(
                    request.activation_id, request.evaluation_id
                ).model_dump(mode="json"),
                args.output,
            )
            return 0
        if args.command == "rill-assist-inspect":
            _emit(assist_service.inspect())
            return 0
        if args.command == "rill-shadow-evaluate":
            _require_rill_writes(settings)
            result = rill_service.evaluate(
                args.parse_run_id,
                structure_id=args.structure_id,
                domain_result_id=args.domain_result_id,
            )
            _emit(result.model_dump(mode="json"), args.output)
            return 0
        if args.command == "rill-shadow-get":
            _emit(rill_service.get(args.evaluation_id).model_dump(mode="json"), args.output)
            return 0
        if args.command == "rill-shadow-feedback":
            _require_rill_writes(settings)
            payload = ShadowFeedbackInput.model_validate_json(
                args.file.read_text(encoding="utf-8")
            )
            _emit(rill_service.feedback(payload).model_dump(mode="json"), args.output)
            return 0
        if args.command == "rill-shadow-inspect":
            _emit(rill_service.inspect())
            return 0
        if args.command == "rill-shadow-replay":
            _emit(rill_service.replay.metrics().model_dump(mode="json"))
            return 0
        if args.command == "rill-shadow-snapshot":
            _require_rill_writes(settings)
            _emit(rill_service.snapshot().model_dump(mode="json"))
            return 0
        if args.command == "rill-shadow-reset":
            _require_rill_writes(settings)
            _emit(rill_service.reset().model_dump(mode="json"))
            return 0
        if args.command == "parsers":
            _emit([item.model_dump(mode="json") for item in orchestrator.registry.health()])
            return 0
        if args.command == "standard-list":
            _emit([item.model_dump(mode="json") for item in library.list_manifests()])
            return 0
        if args.command == "structure-recover":
            _emit(structure_service.recover_run(args.run_id).model_dump(mode="json"), args.output)
            return 0
        if args.command == "structure-get":
            _emit(structure_service.get(args.structure_id).model_dump(mode="json"), args.output)
            return 0
        if args.command == "domain-pack-builtin-list":
            _emit(
                [item.model_dump(mode="json") for item in domain_registry.list_builtin_records()]
            )
            return 0
        if args.command == "domain-pack-install-builtin":
            _require_domain_writes(settings)
            record = domain_registry.install_builtin(args.pack_id)
            if args.activate:
                record = domain_registry.activate(record.pack_id, record.version)
            _emit(record.model_dump(mode="json"))
            return 0
        if args.command == "domain-pack-scaffold":
            target = create_domain_pack_scaffold(
                args.target_parent,
                pack_id=args.pack_id,
                version=args.version,
                template=DomainPackTemplateKind(args.template),
                include_family_profile=not args.without_family_profile,
            )
            _emit({"path": str(target)})
            return 0
        if args.command == "family-detect":
            _require_family_writes(settings)
            _emit(family_service.detect(args.structure_id).model_dump(mode="json"), args.output)
            return 0
        if args.command == "family-get":
            _emit(family_service.get(args.detection_id).model_dump(mode="json"), args.output)
            return 0
        if args.command == "domain-pack-list":
            _emit([item.model_dump(mode="json") for item in domain_registry.list_records()])
            return 0
        if args.command == "domain-pack-install":
            _require_domain_writes(settings)
            record = (
                domain_registry.install_directory(args.path)
                if args.path.is_dir()
                else domain_registry.install_archive(args.path.read_bytes())
            )
            if args.activate:
                record = domain_registry.activate(record.pack_id, record.version)
            _emit(record.model_dump(mode="json"))
            return 0
        if args.command == "domain-pack-activate":
            _require_domain_writes(settings)
            _emit(domain_registry.activate(args.pack_id, args.version).model_dump(mode="json"))
            return 0
        if args.command == "domain-pack-deactivate":
            _require_domain_writes(settings)
            domain_registry.deactivate(args.pack_id)
            _emit({"deactivated": args.pack_id})
            return 0
        if args.command == "domain-pack-uninstall":
            _require_domain_writes(settings)
            domain_registry.uninstall(args.pack_id, args.version)
            _emit({"uninstalled": f"{args.pack_id}@{args.version}"})
            return 0
        if args.command == "domain-apply":
            result = domain_service.apply(
                args.structure_id,
                args.pack_id,
                args.version,
                fallback_on_error=not args.no_fallback,
            )
            _emit(result.model_dump(mode="json"), args.output)
            return 0
        if args.command == "domain-get":
            _emit(domain_service.get(args.domain_result_id).model_dump(mode="json"), args.output)
            return 0
        if args.command == "domain-review-export":
            export = review_service.export_labelu(args.domain_result_id)
            _emit(export.model_dump(mode="json"), args.output)
            return 0
        if args.command == "domain-review-submit":
            _require_domain_writes(settings)
            submission = LabelUReviewSubmission.model_validate_json(
                args.file.read_text(encoding="utf-8")
            )
            _emit(review_service.submit_labelu(submission).model_dump(mode="json"), args.output)
            return 0
        if args.command == "standard-register":
            if not settings.enable_standard_writes:
                raise StandardWriteDisabledError(
                    "standard writes are disabled; set DI_ENABLE_STANDARD_WRITES=true "
                    "in an approved environment"
                )
            manifest = library.register_run(
                args.run_id,
                reviewer=args.reviewer,
                approval_note=args.note,
                approved=args.approved,
            )
            _emit(manifest.model_dump(mode="json"))
            return 0

        content = args.file.read_bytes()
        request = ingest_bytes(
            args.file.name,
            content,
            policy=IngestionPolicy(settings.max_upload_bytes),
            parser_id=(args.parser if args.command == "parse" else None),
            domain_pack=(args.domain_pack if args.command == "parse" else None),
        )
        if args.command == "parse":
            result = orchestrator.parse(request)
            _emit(
                result.model_dump(mode="json", exclude={"raw_output", "binary_artifacts"}),
                args.output,
            )
            return 0
        result = matcher.match(
            request.content,
            request.mime_type,
            page_index=args.page_index,
            query_text=args.query_text,
            top_k=max(1, min(args.top_k, 20)),
        )
        payload: dict[str, object] = {"match": result.model_dump(mode="json")}
        if args.include_standard and result.safe_standard_ref:
            payload["standard_document"] = library.read_document(
                result.candidates[0].standard_id
            ).model_dump(mode="json")
        _emit(payload, args.output)
        return 0
    finally:
        rill_service.close()
        orchestrator.registry.close()


if __name__ == "__main__":
    raise SystemExit(main())
