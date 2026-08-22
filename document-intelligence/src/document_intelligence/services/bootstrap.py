from __future__ import annotations

import hashlib
from pathlib import Path

from document_intelligence.campaign import CampaignStore, QualificationCampaignService
from document_intelligence.config import Settings, load_parser_config
from document_intelligence.domain_runtime import (
    DomainPackRegistry,
    DomainResultStore,
    DomainRuntimeEngine,
    DomainRuntimeService,
)
from document_intelligence.family import (
    DocumentFamilyDetector,
    DocumentFamilyService,
    FamilyDetectionStore,
)
from document_intelligence.production import (
    ProductionQualificationPolicy,
    ProductionQualificationService,
    ProductionQualificationStore,
)
from document_intelligence.mlops import MLOpsService, MLOpsStore
from document_intelligence.parser_sdk import ParserRegistry
from document_intelligence.parsers import (
    MinerUBenchmarkParser,
    NativePdfParser,
    OpenDocParser,
    PaddleParser,
)
from document_intelligence.parsers.http_gateway import HttpNormalizedGatewayParser
from document_intelligence.review import DomainReviewService
from document_intelligence.rill.assist import RillAssistService
from document_intelligence.rill.assist_store import RillAssistStore
from document_intelligence.rill.client import (
    ReferenceRillShadowClient,
    RillShadowClient,
    SubprocessRillClient,
)
from document_intelligence.rill.distribution import RillAdoptionManager
from document_intelligence.rill.stable_client import StableV2RillClient
from document_intelligence.rill.drift import ShadowDriftMonitor
from document_intelligence.rill.features import ShadowFeatureBuilder
from document_intelligence.rill.service import RillShadowService
from document_intelligence.rill.store import RillShadowStore
from document_intelligence.services.orchestrator import ParseOrchestrator
from document_intelligence.services.store import ArtifactStore
from document_intelligence.structure import (
    StructureConfig,
    StructureRecoveryEngine,
    StructureService,
    StructureStore,
)
from document_intelligence.services.visual_catalog import VisualCatalogService


def build_registry(settings: Settings) -> ParserRegistry:
    config = load_parser_config(settings.parser_config)
    registry = ParserRegistry(
        [
            NativePdfParser(
                max_pages=settings.max_pdf_pages,
                max_page_elements=settings.max_page_elements,
                max_binary_artifact_bytes=settings.max_binary_artifact_bytes,
            )
        ]
    )
    registry.register(PaddleParser(config.parsers["paddle"]))
    registry.register(OpenDocParser(config.parsers["opendoc"]))
    registry.register(MinerUBenchmarkParser(config.parsers["mineru-benchmark"]))
    # 自建 OCR 网关（rapidocr onnxruntime），见 ocr-gateway/ocr_gateway.py
    if "rapidocr" in config.parsers:
        registry.register(
            HttpNormalizedGatewayParser("rapidocr", config.parsers["rapidocr"])
        )
    return registry


def build_orchestrator(settings: Settings) -> ParseOrchestrator:
    return ParseOrchestrator(
        build_registry(settings),
        ArtifactStore(settings.workspace),
        max_pages=settings.max_pdf_pages,
        max_document_elements=settings.max_document_elements,
        max_binary_artifact_bytes=settings.max_binary_artifact_bytes,
    )


def build_structure_service(
    settings: Settings,
    artifact_store: ArtifactStore | None = None,
) -> StructureService:
    store = artifact_store or ArtifactStore(settings.workspace)
    config = StructureConfig(
        max_columns=settings.structure_max_columns,
        spanning_width=settings.structure_spanning_width,
        column_gap=settings.structure_column_gap,
        repeated_margin_ratio=settings.structure_repeated_margin_ratio,
        caption_threshold=settings.structure_caption_threshold,
        cross_page_threshold=settings.structure_cross_page_threshold,
    )
    return StructureService(
        store,
        StructureStore(settings.workspace),
        StructureRecoveryEngine(config),
    )


def build_domain_pack_registry(settings: Settings) -> DomainPackRegistry:
    return DomainPackRegistry(
        settings.workspace,
        engine_version=DomainRuntimeEngine.runtime_version,
        require_signatures=settings.domain_pack_require_signatures,
        trusted_public_keys=settings.domain_pack_trusted_public_keys,
        max_archive_files=settings.domain_pack_max_archive_files,
        max_archive_bytes=settings.domain_pack_max_archive_bytes,
        max_compression_ratio=settings.domain_pack_max_compression_ratio,
    )


def build_document_family_service(
    settings: Settings,
    *,
    artifact_store: ArtifactStore | None = None,
    structure_service: StructureService | None = None,
    domain_registry: DomainPackRegistry | None = None,
) -> DocumentFamilyService:
    store = artifact_store or ArtifactStore(settings.workspace)
    structures = structure_service or build_structure_service(settings, store)
    registry = domain_registry or build_domain_pack_registry(settings)
    return DocumentFamilyService(
        store,
        structures,
        registry,
        FamilyDetectionStore(settings.workspace),
        DocumentFamilyDetector(),
        max_profiles=settings.family_detection_max_profiles,
    )


def build_domain_runtime_service(
    settings: Settings,
    *,
    artifact_store: ArtifactStore | None = None,
    structure_service: StructureService | None = None,
    domain_registry: DomainPackRegistry | None = None,
) -> DomainRuntimeService:
    store = artifact_store or ArtifactStore(settings.workspace)
    structures = structure_service or build_structure_service(settings, store)
    registry = domain_registry or build_domain_pack_registry(settings)
    return DomainRuntimeService(
        store,
        structures,
        registry,
        DomainResultStore(settings.workspace),
        DomainRuntimeEngine(),
    )


def build_domain_review_service(
    settings: Settings,
    *,
    artifact_store: ArtifactStore | None = None,
    structure_service: StructureService | None = None,
    domain_service: DomainRuntimeService | None = None,
) -> DomainReviewService:
    store = artifact_store or ArtifactStore(settings.workspace)
    structures = structure_service or build_structure_service(settings, store)
    domains = domain_service or build_domain_runtime_service(
        settings, artifact_store=store, structure_service=structures
    )
    return DomainReviewService(settings.workspace, store, structures, domains)


def build_rill_shadow_service(
    settings: Settings,
    *,
    artifact_store: ArtifactStore | None = None,
    structure_service: StructureService | None = None,
    domain_service: DomainRuntimeService | None = None,
) -> RillShadowService:
    store = artifact_store or ArtifactStore(settings.workspace)
    structures = structure_service or build_structure_service(settings, store)
    domains = domain_service or build_domain_runtime_service(
        settings, artifact_store=store, structure_service=structures
    )
    schema_path = Path(__file__).resolve().parents[1] / "defaults" / "rill_feature_schema.json"
    feature_builder = ShadowFeatureBuilder(
        store,
        structures,
        domains,
        feature_schema_path=schema_path,
    )
    client: RillShadowClient | None = None
    backend_name: str = settings.rill_shadow_backend
    managed_bundle = RillAdoptionManager(settings.workspace).active_bundle()
    runtime_command = settings.rill_runtime_command
    expected_runtime_sha256 = settings.rill_runtime_artifact_sha256
    expected_runtime_version = "1.2.0"
    expected_model_id: str | None = None
    expected_model_version: str | None = None
    expected_handler_id: str | None = None
    expected_handler_version: str | None = None
    expected_capabilities: list[str] | None = None
    if runtime_command is None and managed_bundle is not None:
        if managed_bundle.get("qualification") != "VERIFIED":
            if settings.production_mode and settings.rill_shadow_backend in {
                "stable-v2",
                "subprocess",
            }:
                raise ValueError(
                    "production Stable v2 requires a verified managed Rill adoption bundle"
                )
        else:
            runtime_command = tuple(str(item) for item in managed_bundle.get("command", ()))
            expected_runtime_sha256 = str(managed_bundle["runtime"]["sha256"])
            expected_runtime_version = str(managed_bundle["runtime"]["version"])
            expected_model_id = str(managed_bundle["model"]["id"])
            expected_model_version = str(managed_bundle["model"]["version"])
            expected_handler_id = str(managed_bundle["handler"]["id"])
            expected_handler_version = str(managed_bundle["handler"]["version"])
            expected_capabilities = [str(item) for item in managed_bundle["capabilities"]]
    if settings.rill_shadow_backend in {"stable-v2", "subprocess"} and settings.production_mode:
        if runtime_command is None:
            raise ValueError(
                "production Stable v2 requires a verified managed bundle or explicit command"
            )
        if managed_bundle is None or settings.rill_runtime_command is not None:
            _validate_explicit_stable_v2(settings, runtime_command)
    if settings.rill_shadow_backend in {"stable-v2", "subprocess"} and runtime_command:
        try:
            client = StableV2RillClient(
                runtime_command,
                feature_schema_hash=feature_builder.feature_schema_hash,
                evaluate_capability=settings.rill_evaluate_capability,
                feedback_capability=settings.rill_feedback_capability,
                request_timeout_seconds=settings.rill_request_timeout_seconds,
                startup_timeout_seconds=settings.rill_startup_timeout_seconds,
                max_message_bytes=settings.rill_max_message_bytes,
                expected_runtime_sha256=expected_runtime_sha256,
                expected_runtime_version=expected_runtime_version,
                expected_model_pack_id=expected_model_id,
                expected_model_pack_version=expected_model_version,
                expected_handler_id=expected_handler_id,
                expected_handler_version=expected_handler_version,
                expected_effective_capabilities=expected_capabilities,
            )
        except Exception:
            if settings.production_mode:
                raise
            client = None
            backend_name = "stable-v2-unavailable"
    elif settings.rill_shadow_backend == "preview-v3" and settings.rill_runtime_command:
        try:
            client = SubprocessRillClient(
                settings.rill_runtime_command,
                feature_schema_hash=feature_builder.feature_schema_hash,
                request_timeout_seconds=settings.rill_request_timeout_seconds,
                startup_timeout_seconds=settings.rill_startup_timeout_seconds,
                max_message_bytes=settings.rill_max_message_bytes,
                expected_runtime_sha256=settings.rill_runtime_artifact_sha256,
            )
        except Exception:
            client = None
            backend_name = "preview-v3-unavailable"
    elif (
        settings.rill_shadow_backend == "reference"
        and settings.rill_reference_backend_allowed
    ):
        client = ReferenceRillShadowClient(feature_builder.feature_schema_hash)
    elif settings.rill_shadow_backend == "reference":
        backend_name = "reference-denied"
    return RillShadowService(
        feature_builder,
        RillShadowStore(settings.workspace),
        ShadowDriftMonitor(
            settings.workspace,
            min_samples=settings.rill_drift_min_samples,
            threshold=settings.rill_drift_threshold,
            delta=settings.rill_drift_delta,
        ),
        client=client,
        backend_name=backend_name,
    )


def _validate_explicit_stable_v2(settings: Settings, command: tuple[str, ...]) -> None:
    if not settings.rill_allow_unmanaged_stable_v2:
        raise ValueError(
            "explicit unmanaged Stable v2 requires DI_RILL_ALLOW_UNMANAGED_STABLE_V2=true"
        )
    if not all(
        (settings.rill_runtime_artifact_sha256, settings.rill_model_artifact_sha256,
         settings.rill_handler_artifact_sha256)
    ):
        raise ValueError(
            "explicit unmanaged Stable v2 requires runtime, model and handler SHA-256 digests"
        )
    try:
        model_path = Path(command[command.index("--pack") + 1])
        handler_path = Path(command[command.index("--handler") + 1])
    except (ValueError, IndexError) as exc:
        raise ValueError(
            "explicit unmanaged Stable v2 command must include --pack and --handler"
        ) from exc
    for path, expected in (
        (model_path, settings.rill_model_artifact_sha256),
        (handler_path, settings.rill_handler_artifact_sha256),
    ):
        if path.is_symlink() or not path.is_file():
            raise ValueError("explicit unmanaged Stable v2 package path is not a regular file")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            raise ValueError("explicit unmanaged Stable v2 package digest mismatch")


def build_rill_assist_service(
    settings: Settings,
    *,
    orchestrator: ParseOrchestrator | None = None,
    shadow_service: RillShadowService | None = None,
    artifact_store: ArtifactStore | None = None,
    structure_service: StructureService | None = None,
    domain_service: DomainRuntimeService | None = None,
) -> RillAssistService:
    active_orchestrator = orchestrator or build_orchestrator(settings)
    shadow = shadow_service or build_rill_shadow_service(
        settings,
        artifact_store=artifact_store or active_orchestrator.store,
        structure_service=structure_service,
        domain_service=domain_service,
    )
    service = RillAssistService(
        shadow,
        active_orchestrator,
        RillAssistStore(settings.workspace),
        min_expert_feedback=settings.rill_assist_min_expert_feedback,
        min_production_like_feedback=settings.rill_assist_min_production_like_feedback,
        min_accuracy=settings.rill_assist_min_accuracy,
        min_action_feedback=settings.rill_assist_min_action_feedback,
        qualification_ttl_hours=settings.rill_assist_qualification_ttl_hours,
        runtime_artifact_sha256=settings.rill_runtime_artifact_sha256,
        model_artifact_sha256=settings.rill_model_artifact_sha256,
        handler_artifact_sha256=settings.rill_handler_artifact_sha256,
    )
    active_orchestrator.parser_suspension_checker = service.is_parser_suspended
    return service


def build_mlops_service(
    settings: Settings,
    *,
    shadow_service: RillShadowService | None = None,
    assist_service: RillAssistService | None = None,
    artifact_store: ArtifactStore | None = None,
    structure_service: StructureService | None = None,
    domain_service: DomainRuntimeService | None = None,
    orchestrator: ParseOrchestrator | None = None,
) -> MLOpsService:
    active_orchestrator = orchestrator or build_orchestrator(settings)
    shadow = shadow_service or build_rill_shadow_service(
        settings,
        artifact_store=artifact_store or active_orchestrator.store,
        structure_service=structure_service,
        domain_service=domain_service,
    )
    assist = assist_service or build_rill_assist_service(
        settings,
        orchestrator=active_orchestrator,
        shadow_service=shadow,
        artifact_store=artifact_store or active_orchestrator.store,
        structure_service=structure_service,
        domain_service=domain_service,
    )
    return MLOpsService(
        MLOpsStore(settings.workspace),
        shadow.store,
        assist.store,
        minimum_accuracy=settings.mlops_minimum_accuracy,
        minimum_challenge_improvement=settings.mlops_minimum_challenge_improvement,
        maximum_latency_ms_p95=settings.mlops_maximum_latency_ms_p95,
        maximum_cost_usd_per_document=settings.mlops_maximum_cost_usd_per_document,
        maximum_family_regression=settings.mlops_maximum_family_regression,
        minimum_shadow_samples=settings.mlops_minimum_shadow_samples,
    )


def build_production_qualification_service(
    settings: Settings,
) -> ProductionQualificationService:
    policy = ProductionQualificationPolicy(
        minimum_domains=settings.production_minimum_domains,
        minimum_gold_documents=settings.production_minimum_gold_documents,
        minimum_challenge_documents=settings.production_minimum_challenge_documents,
        minimum_parser_accuracy=settings.production_minimum_parser_accuracy,
        maximum_parser_timeout_rate=settings.production_maximum_parser_timeout_rate,
        maximum_parser_failure_rate=settings.production_maximum_parser_failure_rate,
        minimum_deterministic_replay_rate=(
            settings.production_minimum_deterministic_replay_rate
        ),
        minimum_soak_hours=settings.production_minimum_soak_hours,
        minimum_scale_concurrency=settings.production_minimum_scale_concurrency,
        minimum_scale_documents=settings.production_minimum_scale_documents,
        maximum_scale_error_rate=settings.production_maximum_scale_error_rate,
        minimum_branch_coverage=settings.production_minimum_branch_coverage,
        minimum_pilot_days=settings.production_minimum_pilot_days,
        minimum_pilot_documents=settings.production_minimum_pilot_documents,
        minimum_pilot_expert_reviews=settings.production_minimum_pilot_expert_reviews,
        minimum_pilot_accuracy=settings.production_minimum_pilot_accuracy,
        required_license_components=(
            ("pymupdf",)
            if settings.pdf_render_backend == "pymupdf"
            else ("document-intelligence",)
        ),
    )
    return ProductionQualificationService(
        ProductionQualificationStore(settings.workspace), policy
    )


def build_qualification_campaign_service(
    settings: Settings,
    *,
    production_service: ProductionQualificationService | None = None,
) -> QualificationCampaignService:
    production = production_service or build_production_qualification_service(settings)
    return QualificationCampaignService(
        CampaignStore(
            settings.workspace,
            max_bundle_bytes=settings.qualification_campaign_max_bundle_bytes,
        ),
        production,
        maximum_lease_seconds=settings.qualification_campaign_maximum_lease_seconds,
    )


def build_visual_catalog_service(settings: Settings) -> VisualCatalogService:
    return VisualCatalogService(settings.workspace)
