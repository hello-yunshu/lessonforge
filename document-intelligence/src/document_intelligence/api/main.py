from __future__ import annotations

import asyncio
import hashlib
import hmac
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, AsyncIterator

from fastapi import (
    Body,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Path as PathParameter,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from document_intelligence import __version__
from document_intelligence.campaign import (
    CampaignActorRequest,
    CampaignCreateRequest,
    CampaignFinalizeRequest,
    EvidenceLinkRequest,
    StepCheckpointRequest,
    StepClaimRequest,
    StepHeartbeatRequest,
    StepTransitionRequest,
)
from document_intelligence.config import Settings
from document_intelligence.domain_runtime import DomainExecutionStatus
from document_intelligence.exceptions import (
    DocumentIntelligenceError,
    DomainPackAccessDeniedError,
    DomainPackWriteDisabledError,
    FamilyDetectionAccessDeniedError,
    FamilyDetectionWriteDisabledError,
    RillAccessDeniedError,
    RillAssistAccessDeniedError,
    RillAssistDisabledError,
    RillWriteDisabledError,
    MLOpsAccessDeniedError,
    MLOpsReleaseDisabledError,
    MLOpsWriteDisabledError,
    StandardAccessDeniedError,
    StandardWriteDisabledError,
    ProductionQualificationAccessDeniedError,
    ProductionQualificationWriteDisabledError,
    QualificationCampaignAccessDeniedError,
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
from document_intelligence.matching import (
    MatchDecision,
    MatchResult,
    StandardLibrary,
    StandardMatcher,
)
from document_intelligence.observability import MetricsRegistry, configure_json_logging
from document_intelligence.security import (
    AuthenticationError,
    AuthorizationError,
    ConcurrencyLimitError,
    Principal,
    RateLimitError,
    SecurityManager,
)
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
from document_intelligence.schema import SAFE_ID_PATTERN, SCHEMA_VERSION
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
    build_visual_catalog_service,
    ingest_bytes,
)


class StructureRecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(pattern=SAFE_ID_PATTERN)


class StandardRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(pattern=SAFE_ID_PATTERN)
    reviewer: str = Field(min_length=1, max_length=127)
    approval_note: str = Field(min_length=1, max_length=2000)
    approved: bool = False


class DomainApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    structure_id: str = Field(pattern=SAFE_ID_PATTERN)
    pack_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    pack_version: str | None = Field(default=None, max_length=63)
    fallback_on_error: bool = True


class FamilyDetectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    structure_id: str = Field(pattern=SAFE_ID_PATTERN)


class RillShadowEvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parse_run_id: str = Field(pattern=SAFE_ID_PATTERN)
    structure_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    domain_result_id: str | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    match_result: MatchResult | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    orchestrator = build_orchestrator(runtime_settings)
    policy = IngestionPolicy(max_upload_bytes=runtime_settings.max_upload_bytes)
    standard_library = StandardLibrary(
        orchestrator.store,
        max_render_pixels=runtime_settings.max_render_pixels,
        pdf_render_backend=runtime_settings.pdf_render_backend,
    )
    structure_service = build_structure_service(
        runtime_settings, artifact_store=orchestrator.store
    )
    domain_registry = build_domain_pack_registry(runtime_settings)
    domain_service = build_domain_runtime_service(
        runtime_settings,
        artifact_store=orchestrator.store,
        structure_service=structure_service,
        domain_registry=domain_registry,
    )
    family_service = build_document_family_service(
        runtime_settings,
        artifact_store=orchestrator.store,
        structure_service=structure_service,
        domain_registry=domain_registry,
    )
    review_service = build_domain_review_service(
        runtime_settings,
        artifact_store=orchestrator.store,
        structure_service=structure_service,
        domain_service=domain_service,
    )
    rill_service = build_rill_shadow_service(
        runtime_settings,
        artifact_store=orchestrator.store,
        structure_service=structure_service,
        domain_service=domain_service,
    )
    assist_service = build_rill_assist_service(
        runtime_settings,
        orchestrator=orchestrator,
        shadow_service=rill_service,
        artifact_store=orchestrator.store,
        structure_service=structure_service,
        domain_service=domain_service,
    )
    mlops_service = build_mlops_service(
        runtime_settings,
        orchestrator=orchestrator,
        shadow_service=rill_service,
        assist_service=assist_service,
        artifact_store=orchestrator.store,
        structure_service=structure_service,
        domain_service=domain_service,
    )
    production_service = build_production_qualification_service(runtime_settings)
    campaign_service = build_qualification_campaign_service(
        runtime_settings, production_service=production_service
    )
    visual_catalog_service = build_visual_catalog_service(runtime_settings)
    security = SecurityManager(
        workspace=runtime_settings.workspace,
        production=runtime_settings.production_mode,
        tenant_token_sha256=runtime_settings.api_tenant_tokens_sha256,
        requests_per_minute=runtime_settings.api_requests_per_minute,
        max_concurrent_per_tenant=(
            runtime_settings.api_max_concurrent_requests_per_tenant
        ),
    )
    metrics = MetricsRegistry()
    api_logger = configure_json_logging()
    matcher = StandardMatcher(
        standard_library,
        high_threshold=runtime_settings.match_high_threshold,
        local_threshold=runtime_settings.match_local_threshold,
        min_margin=runtime_settings.match_min_margin,
        min_local_inliers=runtime_settings.match_min_local_inliers,
        max_pdf_pages=runtime_settings.max_pdf_pages,
        max_render_pixels=runtime_settings.max_render_pixels,
        pdf_render_backend=runtime_settings.pdf_render_backend,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        rill_service.close()
        orchestrator.registry.close()

    app = FastAPI(
        title="Document Intelligence API",
        version=__version__,
        description=(
            "Normalized parsing, high-confidence standard matching, generic structure "
            "and isolated Domain Pack runtime API"
        ),
        docs_url=None if runtime_settings.production_mode else "/docs",
        redoc_url=None if runtime_settings.production_mode else "/redoc",
        openapi_url=None if runtime_settings.production_mode else "/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.state.orchestrator = orchestrator
    app.state.standard_library = standard_library
    app.state.matcher = matcher
    app.state.structure_service = structure_service
    app.state.domain_registry = domain_registry
    app.state.domain_service = domain_service
    app.state.family_service = family_service
    app.state.review_service = review_service
    app.state.rill_service = rill_service
    app.state.assist_service = assist_service
    app.state.mlops_service = mlops_service
    app.state.production_service = production_service
    app.state.campaign_service = campaign_service
    app.state.visual_catalog_service = visual_catalog_service
    app.state.security = security
    app.state.metrics = metrics

    def request_principal(request: Request) -> Principal:
        principal = getattr(request.state, "principal", None)
        if not isinstance(principal, Principal):
            raise HTTPException(status_code=401, detail="request is not authenticated")
        return principal

    def require_entitlement(
        request: Request, resource_type: str, resource_id: str
    ) -> None:
        try:
            security.store.require(request_principal(request), resource_type, resource_id)
        except AuthorizationError as exc:
            raise HTTPException(status_code=404, detail="resource not found") from exc

    def grant_entitlement(
        request: Request, resource_type: str, resource_id: str
    ) -> None:
        security.store.grant(request_principal(request), resource_type, resource_id)

    def json_error(status_code: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": code,
                    "severity": "security",
                    "retryable": status_code in {429, 503, 504},
                    "message": message,
                }
            },
        )

    @app.middleware("http")
    async def release_candidate_guard(request: Request, call_next: Any) -> Any:
        request_id = security.request_id(request.headers.get("X-Request-ID"))
        path_class = security.path_class(request.url.path)
        started_at = time.monotonic()
        principal = Principal("development", "local-user", False)
        entered = False
        status_code = 500
        outcome = "failed"
        metrics.request_started()
        try:
            protected = request.url.path.startswith("/v1/")
            if protected:
                principal = security.authenticate(
                    token=request.headers.get("X-API-Token"),
                    tenant_id=request.headers.get("X-Tenant-ID"),
                    subject_id=request.headers.get("X-Subject-ID"),
                )
                request.state.principal = principal
                security.enter_request(principal)
                entered = True
            else:
                request.state.principal = principal
            try:
                response = await asyncio.wait_for(
                    call_next(request),
                    timeout=runtime_settings.api_request_timeout_seconds,
                )
            except TimeoutError:
                response = json_error(504, "REQUEST_TIMEOUT", "request deadline exceeded")
            status_code = int(response.status_code)
            response.headers["X-Request-ID"] = request_id
            outcome = "allowed" if status_code < 400 else "failed"
            return response
        except AuthenticationError as exc:
            status_code = 401
            outcome = "denied"
            response = json_error(
                status_code, "AUTHENTICATION_REQUIRED", str(exc)
            )
            response.headers["X-Request-ID"] = request_id
            return response
        except RateLimitError as exc:
            status_code = 429
            outcome = "limited"
            response = json_error(status_code, "RATE_LIMITED", str(exc))
            response.headers["X-Request-ID"] = request_id
            return response
        except ConcurrencyLimitError as exc:
            status_code = 429
            outcome = "limited"
            response = json_error(status_code, "CONCURRENCY_LIMITED", str(exc))
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            if entered:
                security.exit_request(principal)
            duration = max(0.0, time.monotonic() - started_at)
            final_status = status_code
            metrics.request_finished(request.method, path_class, final_status, duration)
            try:
                security.store.audit(
                    principal=principal,
                    request_id=request_id,
                    method=request.method,
                    path_class=path_class,
                    status_code=final_status,
                    duration_ms=duration * 1000.0,
                    outcome=outcome,
                )
            except Exception:
                api_logger.exception(
                    "access audit write failed",
                    extra={
                        "structured_fields": {
                            "request_id": request_id,
                            "path": path_class,
                        }
                    },
                )
            api_logger.info(
                "request completed",
                extra={
                    "structured_fields": {
                        "request_id": request_id,
                        "tenant_id": principal.tenant_id,
                        "subject_id": principal.subject_id,
                        "method": request.method,
                        "path": path_class,
                        "status_code": final_status,
                        "duration_ms": round(duration * 1000.0, 3),
                    }
                },
            )

    def require_digest_token(token: str | None, expected: str | None, error: Exception) -> None:
        if expected is None or token is None:
            raise error
        actual = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(actual, expected):
            raise error

    def require_standard_access(token: str | None) -> None:
        require_digest_token(
            token,
            runtime_settings.standard_access_token_sha256,
            StandardAccessDeniedError(
                "standard-library access is not configured or the access token is invalid"
            ),
        )

    def require_domain_access(token: str | None) -> None:
        require_digest_token(
            token,
            runtime_settings.domain_pack_access_token_sha256,
            DomainPackAccessDeniedError(
                "domain-pack access is not configured or the access token is invalid"
            ),
        )

    def require_domain_writes() -> None:
        if not runtime_settings.enable_domain_pack_writes:
            raise DomainPackWriteDisabledError(
                "domain-pack writes are disabled; enable them only in an approved environment"
            )

    def require_family_access(token: str | None) -> None:
        require_digest_token(
            token,
            runtime_settings.family_detection_access_token_sha256,
            FamilyDetectionAccessDeniedError(
                "family-detection access is not configured or the access token is invalid"
            ),
        )

    def require_family_writes() -> None:
        if not runtime_settings.enable_family_detection_writes:
            raise FamilyDetectionWriteDisabledError(
                "family-detection writes are disabled; enable only in an approved environment"
            )

    def require_rill_access(token: str | None) -> None:
        require_digest_token(
            token,
            runtime_settings.rill_access_token_sha256,
            RillAccessDeniedError(
                "Rill Shadow access is not configured or the access token is invalid"
            ),
        )

    def require_rill_writes() -> None:
        if not runtime_settings.enable_rill_shadow_writes:
            raise RillWriteDisabledError(
                "Rill Shadow writes are disabled; enable them only in an approved environment"
            )

    def require_assist_access(token: str | None) -> None:
        require_digest_token(
            token,
            runtime_settings.rill_assist_access_token_sha256,
            RillAssistAccessDeniedError(
                "Rill Assist access is not configured or the access token is invalid"
            ),
        )

    def require_assist_writes() -> None:
        if not runtime_settings.enable_rill_assist_writes:
            raise RillAssistDisabledError(
                "Rill Assist writes are disabled; enable only for qualification governance"
            )

    def require_assist_execution() -> None:
        if not runtime_settings.enable_rill_assist_execution:
            raise RillAssistDisabledError(
                "Rill Assist execution is disabled; qualification alone cannot enable actions"
            )

    def require_mlops_access(token: str | None) -> None:
        require_digest_token(
            token,
            runtime_settings.mlops_access_token_sha256,
            MLOpsAccessDeniedError(
                "MLOps access is not configured or the access token is invalid"
            ),
        )

    def require_mlops_writes() -> None:
        if not runtime_settings.enable_mlops_writes:
            raise MLOpsWriteDisabledError(
                "MLOps writes are disabled; enable only in an approved governance environment"
            )

    def require_mlops_release() -> None:
        if not runtime_settings.enable_mlops_release:
            raise MLOpsReleaseDisabledError(
                "MLOps release operations are disabled; registration does not enable promotion"
            )

    def require_production_access(token: str | None) -> None:
        require_digest_token(
            token,
            runtime_settings.production_qualification_access_token_sha256,
            ProductionQualificationAccessDeniedError(
                "production qualification access is not configured or token is invalid"
            ),
        )

    def require_production_writes() -> None:
        if not runtime_settings.enable_production_qualification_writes:
            raise ProductionQualificationWriteDisabledError(
                "production qualification writes are disabled; evidence cannot be registered"
            )

    def require_campaign_access(token: str | None) -> None:
        require_digest_token(
            token,
            runtime_settings.qualification_campaign_access_token_sha256,
            QualificationCampaignAccessDeniedError(
                "qualification campaign access is not configured or token is invalid"
            ),
        )

    def require_campaign_writes() -> None:
        if not runtime_settings.enable_qualification_campaign_writes:
            raise QualificationCampaignWriteDisabledError(
                "qualification campaign writes are disabled"
            )

    @app.exception_handler(DocumentIntelligenceError)
    async def domain_error_handler(_: Any, exc: DocumentIntelligenceError) -> JSONResponse:
        return JSONResponse(
            status_code=int(getattr(exc, "http_status", 422)),
            content={
                "error": {
                    "code": exc.code,
                    "severity": exc.severity,
                    "retryable": bool(getattr(exc, "retryable", False)),
                    "message": str(exc),
                }
            },
        )

    @app.get("/livez")
    def livez() -> dict[str, str]:
        return {"status": "alive", "service": "document-intelligence"}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        checks: dict[str, bool] = {}
        try:
            runtime_settings.workspace.mkdir(parents=True, exist_ok=True)
            probe = runtime_settings.workspace / ".readiness-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            checks["workspace_writable"] = True
        except OSError:
            checks["workspace_writable"] = False
        parser_health = orchestrator.registry.health()
        checks["parser_available"] = any(item.available and item.enabled for item in parser_health)
        checks["single_node_mode"] = runtime_settings.single_node_mode
        checks["production_security_configured"] = (
            not runtime_settings.production_mode
            or bool(runtime_settings.api_tenant_tokens_sha256)
        )
        ready = all(checks.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ready" if ready else "not_ready",
                "service": "document-intelligence",
                "version": __version__,
                "checks": checks,
            },
        )

    @app.get("/metrics", response_class=PlainTextResponse)
    def prometheus_metrics(
        metrics_token: Annotated[str | None, Header(alias="X-Metrics-Token")] = None,
    ) -> PlainTextResponse:
        if runtime_settings.production_mode:
            if runtime_settings.metrics_access_token_sha256 is None:
                raise HTTPException(status_code=404, detail="metrics endpoint is disabled")
            try:
                require_digest_token(
                    metrics_token,
                    runtime_settings.metrics_access_token_sha256,
                    AuthenticationError("invalid metrics credentials"),
                )
            except AuthenticationError as exc:
                raise HTTPException(status_code=401, detail="invalid metrics credentials") from exc
        return PlainTextResponse(
            metrics.render_prometheus(), media_type="text/plain; version=0.0.4"
        )

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "document-intelligence",
            "version": __version__,
            "schema_version": SCHEMA_VERSION,
            "deployment_profile": runtime_settings.deployment_profile,
            "single_node_mode": runtime_settings.single_node_mode,
            "tenant_auth_required": runtime_settings.production_mode,
            "openapi_enabled": not runtime_settings.production_mode,
            "pdf_render_backend": runtime_settings.pdf_render_backend,
            "standard_writes_enabled": runtime_settings.enable_standard_writes,
            "domain_pack_writes_enabled": runtime_settings.enable_domain_pack_writes,
            "domain_pack_signatures_required": runtime_settings.domain_pack_require_signatures,
            "family_detection_writes_enabled": runtime_settings.enable_family_detection_writes,
            "family_detection_advisory_only": True,
            "structure_engine_version": structure_service.engine.engine_version,
            "domain_runtime_version": domain_service.engine.runtime_version,
            "rill_shadow_backend": runtime_settings.rill_shadow_backend,
            "rill_shadow_writes_enabled": runtime_settings.enable_rill_shadow_writes,
            "rill_shadow_only": True,
            "rill_assist_writes_enabled": runtime_settings.enable_rill_assist_writes,
            "rill_assist_execution_enabled": runtime_settings.enable_rill_assist_execution,
            "bounded_auto_enabled": False,
            "mlops_writes_enabled": runtime_settings.enable_mlops_writes,
            "mlops_release_enabled": runtime_settings.enable_mlops_release,
            "production_qualification_writes_enabled": (
                runtime_settings.enable_production_qualification_writes
            ),
            "production_qualified": any(
                report.qualified for report in production_service.store.list_reports()
            ),
            "qualification_campaign_writes_enabled": (
                runtime_settings.enable_qualification_campaign_writes
            ),
        }

    @app.get("/v1/capabilities")
    def capability_matrix() -> dict[str, Any]:
        parsers = [item.model_dump(mode="json") for item in orchestrator.registry.health()]
        return {
            "release_status": "release-candidate",
            "deployment_boundary": "single-node-self-hosted",
            "capabilities": {
                "native_pdf": {"status": "stable-engineering-baseline", "backend": "pypdf"},
                "scanned_ocr": {"status": "disabled-until-qualified"},
                "standard_visual_matching": {
                    "status": (
                        "preview"
                        if runtime_settings.pdf_render_backend == "pymupdf"
                        else "disabled"
                    ),
                    "renderer": runtime_settings.pdf_render_backend,
                },
                "domain_pack_runtime": {"status": "release-candidate", "declarative_only": True},
                "rill_shadow": {"status": "preview", "advisory_only": True},
                "rill_assist": {"status": "qualification-gated-tier1"},
                "bounded_auto": {"status": "unsupported", "enabled": False},
                "multi_node": {"status": "unsupported"},
            },
            "parsers": parsers,
        }

    @app.get("/v1/contracts/freeze")
    async def inspect_frozen_contracts() -> dict[str, Any]:
        service = FreezeService()
        manifest = await run_in_threadpool(service.load_manifest)
        verification = await run_in_threadpool(service.verify)
        return {
            "manifest": manifest.model_dump(mode="json"),
            "verification": verification.model_dump(mode="json"),
        }

    @app.get("/v1/parsers")
    def list_parsers() -> dict[str, Any]:
        parsers = [item.model_dump(mode="json") for item in orchestrator.registry.health()]
        return {"parsers": parsers}

    @app.post("/v1/parse")
    async def parse_document(
        http_request: Request,
        file: Annotated[UploadFile, File()],
        parser_id: Annotated[str, Form()] = "auto",
        domain_pack: Annotated[str | None, Form()] = None,
        include_document: Annotated[bool, Form()] = True,
        page_range: Annotated[str | None, Form()] = None,
    ) -> dict[str, Any]:
        content = await file.read(runtime_settings.max_upload_bytes + 1)
        options: dict[str, object] = {}
        if page_range:
            options["page_range"] = page_range
        parse_request = ingest_bytes(
            file.filename or "upload.bin",
            content,
            policy=policy,
            parser_id=parser_id,
            domain_pack=domain_pack,
            options=options,
        )
        result = await run_in_threadpool(orchestrator.parse, parse_request)
        grant_entitlement(http_request, "run", result.run.parse_run_id)
        grant_entitlement(http_request, "document", result.document.document_id)
        response: dict[str, Any] = {
            "run": result.run.model_dump(mode="json"),
            "document_id": result.document.document_id,
        }
        if include_document:
            response["document"] = result.document.model_dump(mode="json")
        return response

    @app.get("/v1/runs/{run_id}")
    async def get_run(http_request: Request, run_id: str) -> dict[str, Any]:
        require_entitlement(http_request, "run", run_id)
        try:
            result = await run_in_threadpool(orchestrator.store.read_result, run_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        return result.model_dump(mode="json", exclude={"raw_output", "binary_artifacts"})

    @app.post("/v1/structure/recover")
    async def recover_structure(
        http_request: Request,
        payload: Annotated[StructureRecoveryRequest, Body()],
    ) -> dict[str, Any]:
        require_entitlement(http_request, "run", payload.run_id)
        try:
            result = await run_in_threadpool(structure_service.recover_run, payload.run_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        grant_entitlement(http_request, "structure", result.structure_id)
        return {"structure": result.model_dump(mode="json")}

    @app.get("/v1/structures/{structure_id}")
    async def get_structure(
        http_request: Request,
        structure_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
    ) -> dict[str, Any]:
        require_entitlement(http_request, "structure", structure_id)
        try:
            result = await run_in_threadpool(structure_service.get, structure_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="structure not found") from exc
        return {"structure": result.model_dump(mode="json")}

    @app.get("/v1/standard")
    async def list_standard_documents(
        standard_token: Annotated[str | None, Header(alias="X-Standard-Token")] = None,
    ) -> dict[str, Any]:
        require_standard_access(standard_token)
        manifests = await run_in_threadpool(standard_library.list_manifests)
        return {"documents": [item.model_dump(mode="json") for item in manifests]}

    @app.post("/v1/standard/register")
    async def register_standard_document(
        http_request: Request,
        payload: Annotated[StandardRegistrationRequest, Body()],
        standard_token: Annotated[str | None, Header(alias="X-Standard-Token")] = None,
    ) -> dict[str, Any]:
        if not runtime_settings.enable_standard_writes:
            raise StandardWriteDisabledError(
                "standard writes are disabled; set DI_ENABLE_STANDARD_WRITES "
                "only in an approved environment"
            )
        require_standard_access(standard_token)
        require_entitlement(http_request, "run", payload.run_id)
        try:
            manifest = await run_in_threadpool(
                standard_library.register_run,
                payload.run_id,
                reviewer=payload.reviewer,
                approval_note=payload.approval_note,
                approved=payload.approved,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        return {"manifest": manifest.model_dump(mode="json")}

    @app.post("/v1/match")
    async def match_standard_document(
        file: Annotated[UploadFile, File()],
        page_index: Annotated[int, Form()] = 0,
        query_text: Annotated[str | None, Form()] = None,
        top_k: Annotated[int, Form()] = 5,
        include_standard: Annotated[bool, Form()] = False,
        standard_token: Annotated[str | None, Header(alias="X-Standard-Token")] = None,
    ) -> dict[str, Any]:
        if include_standard:
            require_standard_access(standard_token)
        content = await file.read(runtime_settings.max_upload_bytes + 1)
        request = ingest_bytes(file.filename or "query.bin", content, policy=policy, parser_id=None)
        result = await run_in_threadpool(
            matcher.match,
            request.content,
            request.mime_type,
            page_index=page_index,
            query_text=query_text,
            top_k=max(1, min(top_k, 20)),
        )
        response: dict[str, Any] = {"match": result.model_dump(mode="json")}
        if include_standard and result.decision == MatchDecision.SAFE_STANDARD_REUSE:
            standard_document = await run_in_threadpool(
                standard_library.read_document, result.candidates[0].standard_id
            )
            response["standard_document"] = standard_document.model_dump(mode="json")
        return response

    @app.get("/v1/domain-packs")
    async def list_domain_packs(
        domain_token: Annotated[str | None, Header(alias="X-Domain-Pack-Token")] = None,
    ) -> dict[str, Any]:
        require_domain_access(domain_token)
        records = await run_in_threadpool(domain_registry.list_records)
        return {"domain_packs": [item.model_dump(mode="json") for item in records]}

    @app.get("/v1/domain-packs/builtin")
    async def list_builtin_domain_packs(
        domain_token: Annotated[str | None, Header(alias="X-Domain-Pack-Token")] = None,
    ) -> dict[str, Any]:
        require_domain_access(domain_token)
        records = await run_in_threadpool(domain_registry.list_builtin_records)
        return {"domain_packs": [item.model_dump(mode="json") for item in records]}

    @app.post("/v1/domain-packs/builtin/{pack_id}/install")
    async def install_builtin_domain_pack(
        pack_id: Annotated[str, PathParameter(pattern=r"^[a-z][a-z0-9-]{0,62}$")],
        activate: bool = False,
        domain_token: Annotated[str | None, Header(alias="X-Domain-Pack-Token")] = None,
    ) -> dict[str, Any]:
        require_domain_writes()
        require_domain_access(domain_token)
        try:
            record = await run_in_threadpool(domain_registry.install_builtin, pack_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="built-in domain pack not found") from exc
        if activate:
            record = await run_in_threadpool(
                domain_registry.activate, record.pack_id, record.version
            )
        return {"domain_pack": record.model_dump(mode="json")}

    @app.post("/v1/domain-packs/install")
    async def install_domain_pack(
        file: Annotated[UploadFile, File()],
        domain_token: Annotated[str | None, Header(alias="X-Domain-Pack-Token")] = None,
    ) -> dict[str, Any]:
        require_domain_writes()
        require_domain_access(domain_token)
        archive = await file.read(runtime_settings.domain_pack_max_archive_bytes + 1)
        record = await run_in_threadpool(domain_registry.install_archive, archive)
        return {"domain_pack": record.model_dump(mode="json")}

    @app.post("/v1/domain-packs/{pack_id}/{version}/activate")
    async def activate_domain_pack(
        pack_id: Annotated[str, PathParameter(pattern=r"^[a-z][a-z0-9-]{0,62}$")],
        version: str,
        domain_token: Annotated[str | None, Header(alias="X-Domain-Pack-Token")] = None,
    ) -> dict[str, Any]:
        require_domain_writes()
        require_domain_access(domain_token)
        record = await run_in_threadpool(domain_registry.activate, pack_id, version)
        return {"domain_pack": record.model_dump(mode="json")}

    @app.post("/v1/domain-packs/{pack_id}/deactivate")
    async def deactivate_domain_pack(
        pack_id: Annotated[str, PathParameter(pattern=r"^[a-z][a-z0-9-]{0,62}$")],
        domain_token: Annotated[str | None, Header(alias="X-Domain-Pack-Token")] = None,
    ) -> dict[str, Any]:
        require_domain_writes()
        require_domain_access(domain_token)
        await run_in_threadpool(domain_registry.deactivate, pack_id)
        return {"deactivated": pack_id}

    @app.delete("/v1/domain-packs/{pack_id}/{version}")
    async def uninstall_domain_pack(
        pack_id: Annotated[str, PathParameter(pattern=r"^[a-z][a-z0-9-]{0,62}$")],
        version: str,
        domain_token: Annotated[str | None, Header(alias="X-Domain-Pack-Token")] = None,
    ) -> dict[str, Any]:
        require_domain_writes()
        require_domain_access(domain_token)
        await run_in_threadpool(domain_registry.uninstall, pack_id, version)
        return {"uninstalled": f"{pack_id}@{version}"}

    @app.post("/v1/family/detect")
    async def detect_document_family(
        http_request: Request,
        payload: Annotated[FamilyDetectionRequest, Body()],
        family_token: Annotated[str | None, Header(alias="X-Family-Detection-Token")] = None,
    ) -> dict[str, Any]:
        require_family_writes()
        require_family_access(family_token)
        require_entitlement(http_request, "structure", payload.structure_id)
        try:
            result = await run_in_threadpool(family_service.detect, payload.structure_id)
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404,
                detail="structure or active family pack not found",
            ) from exc
        grant_entitlement(http_request, "family-detection", result.detection_id)
        return {"family_detection": result.model_dump(mode="json")}

    @app.get("/v1/family-detections/{detection_id}")
    async def get_document_family_detection(
        http_request: Request,
        detection_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        family_token: Annotated[str | None, Header(alias="X-Family-Detection-Token")] = None,
    ) -> dict[str, Any]:
        require_family_access(family_token)
        require_entitlement(http_request, "family-detection", detection_id)
        try:
            result = await run_in_threadpool(family_service.get, detection_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="family detection not found") from exc
        return {"family_detection": result.model_dump(mode="json")}

    @app.post("/v1/domain/apply")
    async def apply_domain_pack(
        http_request: Request, payload: Annotated[DomainApplyRequest, Body()]
    ) -> dict[str, Any]:
        require_entitlement(http_request, "structure", payload.structure_id)
        try:
            result = await run_in_threadpool(
                domain_service.apply,
                payload.structure_id,
                payload.pack_id,
                payload.pack_version,
                fallback_on_error=payload.fallback_on_error,
            )
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail="structure or domain pack not found"
            ) from exc
        grant_entitlement(http_request, "domain-result", result.domain_result_id)
        response: dict[str, Any] = {"domain_result": result.model_dump(mode="json")}
        if result.status == DomainExecutionStatus.FALLBACK_GENERIC:
            structure = await run_in_threadpool(structure_service.get, result.structure_id)
            response["generic_structure"] = structure.model_dump(mode="json")
        return response

    @app.get("/v1/domain-results/{domain_result_id}")
    async def get_domain_result(
        http_request: Request,
        domain_result_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
    ) -> dict[str, Any]:
        require_entitlement(http_request, "domain-result", domain_result_id)
        try:
            result = await run_in_threadpool(domain_service.get, domain_result_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="domain result not found") from exc
        return {"domain_result": result.model_dump(mode="json")}

    @app.post("/v1/domain-results/{domain_result_id}/review/export")
    async def export_domain_review(
        http_request: Request,
        domain_result_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        domain_token: Annotated[str | None, Header(alias="X-Domain-Pack-Token")] = None,
    ) -> dict[str, Any]:
        require_domain_access(domain_token)
        require_entitlement(http_request, "domain-result", domain_result_id)
        export = await run_in_threadpool(review_service.export_labelu, domain_result_id)
        return {"review_export": export.model_dump(mode="json")}

    @app.post("/v1/domain-reviews")
    async def submit_domain_review(
        submission: Annotated[LabelUReviewSubmission, Body()],
        domain_token: Annotated[str | None, Header(alias="X-Domain-Pack-Token")] = None,
    ) -> dict[str, Any]:
        require_domain_writes()
        require_domain_access(domain_token)
        record = await run_in_threadpool(review_service.submit_labelu, submission)
        return {"review": record.model_dump(mode="json")}

    @app.post("/v1/rill/shadow/evaluate")
    async def evaluate_rill_shadow(
        http_request: Request,
        payload: Annotated[RillShadowEvaluateRequest, Body()],
        rill_token: Annotated[str | None, Header(alias="X-Rill-Token")] = None,
    ) -> dict[str, Any]:
        require_rill_writes()
        require_rill_access(rill_token)
        require_entitlement(http_request, "run", payload.parse_run_id)
        if payload.structure_id is not None:
            require_entitlement(http_request, "structure", payload.structure_id)
        if payload.domain_result_id is not None:
            require_entitlement(http_request, "domain-result", payload.domain_result_id)
        try:
            evaluation = await run_in_threadpool(
                rill_service.evaluate,
                payload.parse_run_id,
                structure_id=payload.structure_id,
                domain_result_id=payload.domain_result_id,
                match_result=payload.match_result,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="source artifact not found") from exc
        grant_entitlement(http_request, "rill-evaluation", evaluation.evaluation_id)
        return {"shadow_evaluation": evaluation.model_dump(mode="json")}

    @app.get("/v1/rill/shadow/evaluations/{evaluation_id}")
    async def get_rill_shadow_evaluation(
        http_request: Request,
        evaluation_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        rill_token: Annotated[str | None, Header(alias="X-Rill-Token")] = None,
    ) -> dict[str, Any]:
        require_rill_access(rill_token)
        require_entitlement(http_request, "rill-evaluation", evaluation_id)
        try:
            evaluation = await run_in_threadpool(rill_service.get, evaluation_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="shadow evaluation not found") from exc
        return {"shadow_evaluation": evaluation.model_dump(mode="json")}

    @app.post("/v1/rill/shadow/feedback")
    async def submit_rill_shadow_feedback(
        payload: Annotated[ShadowFeedbackInput, Body()],
        rill_token: Annotated[str | None, Header(alias="X-Rill-Token")] = None,
    ) -> dict[str, Any]:
        require_rill_writes()
        require_rill_access(rill_token)
        record = await run_in_threadpool(rill_service.feedback, payload)
        return {"shadow_feedback": record.model_dump(mode="json")}

    @app.get("/v1/rill/shadow/replay")
    async def rill_shadow_replay(
        rill_token: Annotated[str | None, Header(alias="X-Rill-Token")] = None,
    ) -> dict[str, Any]:
        require_rill_access(rill_token)
        metrics = await run_in_threadpool(rill_service.replay.metrics)
        return {"replay": metrics.model_dump(mode="json")}

    @app.get("/v1/rill/shadow/inspect")
    async def inspect_rill_shadow(
        rill_token: Annotated[str | None, Header(alias="X-Rill-Token")] = None,
    ) -> dict[str, Any]:
        require_rill_access(rill_token)
        return await run_in_threadpool(rill_service.inspect)

    @app.post("/v1/rill/shadow/snapshot")
    async def snapshot_rill_shadow(
        rill_token: Annotated[str | None, Header(alias="X-Rill-Token")] = None,
    ) -> dict[str, Any]:
        require_rill_writes()
        require_rill_access(rill_token)
        record = await run_in_threadpool(rill_service.snapshot)
        return {"snapshot": record.model_dump(mode="json")}

    @app.post("/v1/rill/shadow/reset")
    async def reset_rill_shadow(
        rill_token: Annotated[str | None, Header(alias="X-Rill-Token")] = None,
    ) -> dict[str, Any]:
        require_rill_writes()
        require_rill_access(rill_token)
        record = await run_in_threadpool(rill_service.reset)
        return {"reset": record.model_dump(mode="json")}

    @app.post("/v1/rill/assist/attest")
    async def attest_rill_assist_evidence(
        payload: Annotated[AssistAttestationRequest, Body()],
        assist_token: Annotated[str | None, Header(alias="X-Rill-Assist-Token")] = None,
    ) -> dict[str, Any]:
        require_assist_writes()
        require_assist_access(assist_token)
        record = await run_in_threadpool(assist_service.create_attestation, payload)
        return {"assist_attestation": record.model_dump(mode="json")}

    @app.post("/v1/rill/assist/qualify")
    async def qualify_rill_assist(
        payload: Annotated[AssistQualificationRequest, Body()],
        assist_token: Annotated[str | None, Header(alias="X-Rill-Assist-Token")] = None,
    ) -> dict[str, Any]:
        require_assist_writes()
        require_assist_access(assist_token)
        report = await run_in_threadpool(assist_service.qualify, payload.requested_actions)
        return {"assist_qualification": report.model_dump(mode="json")}

    @app.get("/v1/rill/assist/qualifications/{report_id}")
    async def get_rill_assist_qualification(
        report_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        assist_token: Annotated[str | None, Header(alias="X-Rill-Assist-Token")] = None,
    ) -> dict[str, Any]:
        require_assist_access(assist_token)
        try:
            report = await run_in_threadpool(assist_service.store.read_qualification, report_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Assist qualification not found") from exc
        return {"assist_qualification": report.model_dump(mode="json")}

    @app.post("/v1/rill/assist/activate")
    async def activate_rill_assist(
        payload: Annotated[AssistActivationRequest, Body()],
        assist_token: Annotated[str | None, Header(alias="X-Rill-Assist-Token")] = None,
    ) -> dict[str, Any]:
        require_assist_writes()
        require_assist_access(assist_token)
        activation = await run_in_threadpool(assist_service.activate, payload)
        return {"assist_activation": activation.model_dump(mode="json")}

    @app.post("/v1/rill/assist/revoke")
    async def revoke_rill_assist(
        payload: Annotated[AssistRevocationRequest, Body()],
        assist_token: Annotated[str | None, Header(alias="X-Rill-Assist-Token")] = None,
    ) -> dict[str, Any]:
        require_assist_writes()
        require_assist_access(assist_token)
        revocation = await run_in_threadpool(assist_service.revoke, payload)
        return {"assist_revocation": revocation.model_dump(mode="json")}

    @app.post("/v1/rill/assist/parsers/suspend")
    async def suspend_rill_assist_parser(
        payload: Annotated[AssistParserSuspensionRequest, Body()],
        assist_token: Annotated[str | None, Header(alias="X-Rill-Assist-Token")] = None,
    ) -> dict[str, Any]:
        require_assist_writes()
        require_assist_execution()
        require_assist_access(assist_token)
        record = await run_in_threadpool(assist_service.suspend_parser, payload)
        return {"parser_suspension": record.model_dump(mode="json")}

    @app.post("/v1/rill/assist/parsers/resume")
    async def resume_rill_assist_parser(
        payload: Annotated[AssistParserResumeRequest, Body()],
        assist_token: Annotated[str | None, Header(alias="X-Rill-Assist-Token")] = None,
    ) -> dict[str, Any]:
        require_assist_writes()
        require_assist_execution()
        require_assist_access(assist_token)
        record = await run_in_threadpool(assist_service.resume_parser, payload)
        return {"parser_resume": record.model_dump(mode="json")}

    @app.post("/v1/rill/assist/execute")
    async def execute_rill_assist(
        payload: Annotated[AssistExecutionRequest, Body()],
        assist_token: Annotated[str | None, Header(alias="X-Rill-Assist-Token")] = None,
    ) -> dict[str, Any]:
        require_assist_writes()
        require_assist_execution()
        require_assist_access(assist_token)
        execution = await run_in_threadpool(
            assist_service.execute, payload.activation_id, payload.evaluation_id
        )
        return {"assist_execution": execution.model_dump(mode="json")}

    @app.get("/v1/rill/assist/inspect")
    async def inspect_rill_assist(
        assist_token: Annotated[str | None, Header(alias="X-Rill-Assist-Token")] = None,
    ) -> dict[str, Any]:
        require_assist_access(assist_token)
        return await run_in_threadpool(assist_service.inspect)


    @app.post("/v1/mlops/active-learning/select")
    async def select_active_learning(
        max_items: int = 100,
        max_per_family: int = 20,
        mlops_token: Annotated[str | None, Header(alias="X-MLOps-Token")] = None,
    ) -> dict[str, Any]:
        require_mlops_writes()
        require_mlops_access(mlops_token)
        batch = await run_in_threadpool(
            mlops_service.select_active_learning,
            max_items=max_items,
            max_per_family=max_per_family,
        )
        return {"active_learning_batch": batch.model_dump(mode="json")}

    @app.post("/v1/mlops/datasets")
    async def create_dataset_snapshot(
        payload: Annotated[DatasetSnapshotRequest, Body()],
        mlops_token: Annotated[str | None, Header(alias="X-MLOps-Token")] = None,
    ) -> dict[str, Any]:
        require_mlops_writes()
        require_mlops_access(mlops_token)
        record = await run_in_threadpool(mlops_service.create_snapshot, payload)
        return {"dataset_snapshot": record.model_dump(mode="json")}

    @app.post("/v1/mlops/mlflow-runs")
    async def record_mlflow_run(
        payload: Annotated[MLflowRunRequest, Body()],
        mlops_token: Annotated[str | None, Header(alias="X-MLOps-Token")] = None,
    ) -> dict[str, Any]:
        require_mlops_writes()
        require_mlops_access(mlops_token)
        record = await run_in_threadpool(mlops_service.record_mlflow_run, payload)
        return {"mlflow_run": record.model_dump(mode="json")}

    @app.post("/v1/mlops/candidates")
    async def register_candidate(
        payload: Annotated[CandidateRegistrationRequest, Body()],
        mlops_token: Annotated[str | None, Header(alias="X-MLOps-Token")] = None,
    ) -> dict[str, Any]:
        require_mlops_writes()
        require_mlops_access(mlops_token)
        record = await run_in_threadpool(mlops_service.register_candidate, payload)
        return {"candidate": record.model_dump(mode="json")}

    @app.post("/v1/mlops/evaluations")
    async def evaluate_candidate(
        payload: Annotated[EvaluationRequest, Body()],
        mlops_token: Annotated[str | None, Header(alias="X-MLOps-Token")] = None,
    ) -> dict[str, Any]:
        require_mlops_writes()
        require_mlops_access(mlops_token)
        record = await run_in_threadpool(mlops_service.evaluate, payload)
        return {"candidate_evaluation": record.model_dump(mode="json")}

    @app.post("/v1/mlops/shadow-validations")
    async def record_shadow_validation(
        payload: Annotated[ShadowValidationRequest, Body()],
        mlops_token: Annotated[str | None, Header(alias="X-MLOps-Token")] = None,
    ) -> dict[str, Any]:
        require_mlops_writes()
        require_mlops_access(mlops_token)
        record = await run_in_threadpool(mlops_service.record_shadow_validation, payload)
        return {"shadow_validation": record.model_dump(mode="json")}

    @app.post("/v1/mlops/approvals")
    async def approve_candidate(
        payload: Annotated[ApprovalRequest, Body()],
        mlops_token: Annotated[str | None, Header(alias="X-MLOps-Token")] = None,
    ) -> dict[str, Any]:
        require_mlops_writes()
        require_mlops_access(mlops_token)
        record = await run_in_threadpool(mlops_service.approve, payload)
        return {"release_approval": record.model_dump(mode="json")}

    @app.post("/v1/mlops/promote/shadow")
    async def promote_candidate_to_shadow(
        payload: Annotated[PromoteRequest, Body()],
        mlops_token: Annotated[str | None, Header(alias="X-MLOps-Token")] = None,
    ) -> dict[str, Any]:
        require_mlops_writes()
        require_mlops_release()
        require_mlops_access(mlops_token)
        record = await run_in_threadpool(mlops_service.promote_to_shadow, payload)
        return {"alias_update": record.model_dump(mode="json")}

    @app.post("/v1/mlops/promote/champion")
    async def promote_candidate_to_champion(
        payload: Annotated[PromoteRequest, Body()],
        mlops_token: Annotated[str | None, Header(alias="X-MLOps-Token")] = None,
    ) -> dict[str, Any]:
        require_mlops_writes()
        require_mlops_release()
        require_mlops_access(mlops_token)
        record = await run_in_threadpool(mlops_service.promote_to_champion, payload)
        return {"alias_update": record.model_dump(mode="json")}

    @app.post("/v1/mlops/rollback")
    async def rollback_champion(
        payload: Annotated[RollbackRequest, Body()],
        mlops_token: Annotated[str | None, Header(alias="X-MLOps-Token")] = None,
    ) -> dict[str, Any]:
        require_mlops_writes()
        require_mlops_release()
        require_mlops_access(mlops_token)
        record = await run_in_threadpool(mlops_service.rollback, payload)
        return {"rollback": record.model_dump(mode="json")}

    @app.get("/v1/mlops/lineage/{candidate_id}")
    async def get_candidate_lineage(
        candidate_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        mlops_token: Annotated[str | None, Header(alias="X-MLOps-Token")] = None,
    ) -> dict[str, Any]:
        require_mlops_access(mlops_token)
        try:
            return await run_in_threadpool(mlops_service.lineage, candidate_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="candidate not found") from exc

    @app.get("/v1/mlops/inspect")
    async def inspect_mlops(
        mlops_token: Annotated[str | None, Header(alias="X-MLOps-Token")] = None,
    ) -> dict[str, Any]:
        require_mlops_access(mlops_token)
        return await run_in_threadpool(mlops_service.inspect)

    @app.post("/v1/qualification-campaigns/bundles/import")
    async def import_qualification_campaign_bundle(
        file: Annotated[UploadFile, File()],
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
        production_token: Annotated[
            str | None, Header(alias="X-DI-Production-Token")
        ] = None,
    ) -> dict[str, object]:
        require_campaign_writes()
        require_production_writes()
        require_campaign_access(token)
        require_production_access(production_token)
        raw = await file.read(runtime_settings.qualification_campaign_max_bundle_bytes + 1)
        if len(raw) > runtime_settings.qualification_campaign_max_bundle_bytes:
            raise HTTPException(status_code=413, detail="campaign bundle exceeds configured limit")
        with tempfile.TemporaryDirectory(prefix="di-campaign-import-") as value:
            path = Path(value) / "campaign.zip"
            path.write_bytes(raw)
            restored = await run_in_threadpool(campaign_service.import_bundle, path)
        return {"campaign": restored.model_dump(mode="json")}

    @app.post("/v1/qualification-campaigns")
    async def create_qualification_campaign(
        payload: CampaignCreateRequest,
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        require_campaign_writes()
        require_campaign_access(token)
        value = await run_in_threadpool(campaign_service.create, payload)
        return {"campaign": value.model_dump(mode="json")}

    @app.get("/v1/qualification-campaigns/inspect")
    async def inspect_qualification_campaigns(
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        require_campaign_access(token)
        return await run_in_threadpool(campaign_service.inspect)

    @app.get("/v1/qualification-campaigns/{campaign_id}")
    async def get_qualification_campaign(
        campaign_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        require_campaign_access(token)
        value = await run_in_threadpool(campaign_service.snapshot, campaign_id)
        return {"campaign": value.model_dump(mode="json")}

    async def _campaign_actor_transition(
        operation: Any, campaign_id: str, payload: CampaignActorRequest, token: str | None
    ) -> dict[str, object]:
        require_campaign_writes()
        require_campaign_access(token)
        value = await run_in_threadpool(operation, campaign_id, payload)
        return {"campaign": value.model_dump(mode="json")}

    @app.post("/v1/qualification-campaigns/{campaign_id}/start")
    async def start_qualification_campaign(
        campaign_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        payload: CampaignActorRequest,
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        return await _campaign_actor_transition(campaign_service.start, campaign_id, payload, token)

    @app.post("/v1/qualification-campaigns/{campaign_id}/pause")
    async def pause_qualification_campaign(
        campaign_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        payload: CampaignActorRequest,
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        return await _campaign_actor_transition(campaign_service.pause, campaign_id, payload, token)

    @app.post("/v1/qualification-campaigns/{campaign_id}/resume")
    async def resume_qualification_campaign(
        campaign_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        payload: CampaignActorRequest,
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        return await _campaign_actor_transition(
            campaign_service.resume, campaign_id, payload, token
        )

    @app.post("/v1/qualification-campaigns/{campaign_id}/cancel")
    async def cancel_qualification_campaign(
        campaign_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        payload: CampaignActorRequest,
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        return await _campaign_actor_transition(
            campaign_service.cancel, campaign_id, payload, token
        )

    @app.post("/v1/qualification-campaigns/{campaign_id}/steps/{step_id}/claim")
    async def claim_qualification_step(
        campaign_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        step_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        payload: StepClaimRequest,
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        require_campaign_writes()
        require_campaign_access(token)
        value = await run_in_threadpool(campaign_service.claim, campaign_id, step_id, payload)
        return {"campaign": value.model_dump(mode="json")}

    @app.post("/v1/qualification-campaigns/{campaign_id}/steps/{step_id}/heartbeat")
    async def heartbeat_qualification_step(
        campaign_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        step_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        payload: StepHeartbeatRequest,
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        require_campaign_writes()
        require_campaign_access(token)
        value = await run_in_threadpool(campaign_service.heartbeat, campaign_id, step_id, payload)
        return {"campaign": value.model_dump(mode="json")}

    @app.post("/v1/qualification-campaigns/{campaign_id}/steps/{step_id}/checkpoint")
    async def checkpoint_qualification_step(
        campaign_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        step_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        payload: StepCheckpointRequest,
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        require_campaign_writes()
        require_campaign_access(token)
        value = await run_in_threadpool(campaign_service.checkpoint, campaign_id, step_id, payload)
        return {"campaign": value.model_dump(mode="json")}

    @app.post("/v1/qualification-campaigns/{campaign_id}/steps/{step_id}/evidence")
    async def link_qualification_step_evidence(
        campaign_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        step_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        payload: EvidenceLinkRequest,
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        require_campaign_writes()
        require_campaign_access(token)
        value = await run_in_threadpool(
            campaign_service.link_evidence, campaign_id, step_id, payload
        )
        return {"campaign": value.model_dump(mode="json")}

    @app.post("/v1/qualification-campaigns/{campaign_id}/steps/{step_id}/complete")
    async def complete_qualification_step(
        campaign_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        step_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        payload: StepTransitionRequest,
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        require_campaign_writes()
        require_campaign_access(token)
        value = await run_in_threadpool(
            campaign_service.complete_step, campaign_id, step_id, payload
        )
        return {"campaign": value.model_dump(mode="json")}

    @app.post("/v1/qualification-campaigns/{campaign_id}/steps/{step_id}/fail")
    async def fail_qualification_step(
        campaign_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        step_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        payload: StepTransitionRequest,
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        require_campaign_writes()
        require_campaign_access(token)
        value = await run_in_threadpool(campaign_service.fail_step, campaign_id, step_id, payload)
        return {"campaign": value.model_dump(mode="json")}

    @app.post("/v1/qualification-campaigns/{campaign_id}/steps/{step_id}/retry")
    async def retry_qualification_step(
        campaign_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        step_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        payload: CampaignActorRequest,
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        require_campaign_writes()
        require_campaign_access(token)
        value = await run_in_threadpool(campaign_service.retry_step, campaign_id, step_id, payload)
        return {"campaign": value.model_dump(mode="json")}

    @app.post("/v1/qualification-campaigns/{campaign_id}/finalize")
    async def finalize_qualification_campaign(
        campaign_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        payload: CampaignFinalizeRequest,
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        require_campaign_writes()
        require_campaign_access(token)
        value = await run_in_threadpool(campaign_service.finalize, campaign_id, payload)
        return {"campaign": value.model_dump(mode="json")}

    @app.post("/v1/qualification-campaigns/{campaign_id}/bundle")
    async def export_qualification_campaign_bundle(
        campaign_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        token: Annotated[str | None, Header(alias="X-DI-Access-Token")] = None,
    ) -> dict[str, object]:
        require_campaign_writes()
        require_campaign_access(token)
        output = campaign_service.store.exports / f"{campaign_id}.zip"
        if output.exists():
            result = await run_in_threadpool(campaign_service.verify_bundle, output)
        else:
            result = await run_in_threadpool(
                campaign_service.export_bundle, campaign_id, output
            )
        return {"bundle": result["bundle"]}

    @app.post("/v1/production/evidence/datasets")
    async def record_production_dataset(
        payload: Annotated[DatasetQualificationRequest, Body()],
        token: Annotated[str | None, Header(alias="X-Production-Qualification-Token")] = None,
    ) -> dict[str, Any]:
        require_production_writes()
        require_production_access(token)
        record = await run_in_threadpool(production_service.record_dataset, payload)
        return {"dataset_qualification_evidence": record.model_dump(mode="json")}

    @app.post("/v1/production/evidence/parsers")
    async def record_production_parser(
        payload: Annotated[ParserQualificationRequest, Body()],
        token: Annotated[str | None, Header(alias="X-Production-Qualification-Token")] = None,
    ) -> dict[str, Any]:
        require_production_writes()
        require_production_access(token)
        record = await run_in_threadpool(production_service.record_parser, payload)
        return {"parser_qualification_evidence": record.model_dump(mode="json")}

    @app.post("/v1/production/evidence/scale")
    async def record_production_scale(
        payload: Annotated[ScaleQualificationRequest, Body()],
        token: Annotated[str | None, Header(alias="X-Production-Qualification-Token")] = None,
    ) -> dict[str, Any]:
        require_production_writes()
        require_production_access(token)
        record = await run_in_threadpool(production_service.record_scale, payload)
        return {"scale_qualification_evidence": record.model_dump(mode="json")}

    @app.post("/v1/production/evidence/supply-chain")
    async def record_production_supply_chain(
        payload: Annotated[SupplyChainQualificationRequest, Body()],
        token: Annotated[str | None, Header(alias="X-Production-Qualification-Token")] = None,
    ) -> dict[str, Any]:
        require_production_writes()
        require_production_access(token)
        record = await run_in_threadpool(production_service.record_supply_chain, payload)
        return {"supply_chain_qualification_evidence": record.model_dump(mode="json")}

    @app.post("/v1/production/evidence/licenses")
    async def record_production_license(
        payload: Annotated[LicenseQualificationRequest, Body()],
        token: Annotated[str | None, Header(alias="X-Production-Qualification-Token")] = None,
    ) -> dict[str, Any]:
        require_production_writes()
        require_production_access(token)
        record = await run_in_threadpool(production_service.record_license, payload)
        return {"license_qualification_evidence": record.model_dump(mode="json")}

    @app.post("/v1/production/evidence/pilots")
    async def record_production_pilot(
        payload: Annotated[PilotQualificationRequest, Body()],
        token: Annotated[str | None, Header(alias="X-Production-Qualification-Token")] = None,
    ) -> dict[str, Any]:
        require_production_writes()
        require_production_access(token)
        record = await run_in_threadpool(production_service.record_pilot, payload)
        return {"pilot_qualification_evidence": record.model_dump(mode="json")}

    @app.post("/v1/production/qualify")
    async def qualify_production(
        payload: Annotated[ProductionQualificationRequest, Body()],
        token: Annotated[str | None, Header(alias="X-Production-Qualification-Token")] = None,
    ) -> dict[str, Any]:
        require_production_writes()
        require_production_access(token)
        report = await run_in_threadpool(production_service.qualify, payload)
        return {"production_qualification": report.model_dump(mode="json")}

    @app.get("/v1/production/reports/{report_id}")
    async def get_production_report(
        report_id: Annotated[str, PathParameter(pattern=SAFE_ID_PATTERN)],
        token: Annotated[str | None, Header(alias="X-Production-Qualification-Token")] = None,
    ) -> dict[str, Any]:
        require_production_access(token)
        try:
            report = await run_in_threadpool(production_service.store.read_report, report_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="production report not found") from exc
        return {"production_qualification": report.model_dump(mode="json")}

    @app.get("/v1/production/inspect")
    async def inspect_production_qualification(
        token: Annotated[str | None, Header(alias="X-Production-Qualification-Token")] = None,
    ) -> dict[str, Any]:
        require_production_access(token)
        return await run_in_threadpool(production_service.inspect)

    # 教材编排模块（独立板块，与核心 API 解耦，可单独更新）
    from document_intelligence.api.textbook import router as textbook_router

    app.include_router(textbook_router)

    # ---- 视觉语义目录（先识别图标/角色，再解析板块） ----
    @app.get("/v1/visual-semantic/profiles")
    async def list_visual_semantic_profiles(request: Request) -> dict[str, Any]:
        service = request.app.state.visual_catalog_service
        return {"profiles": service.profiles()}

    @app.post("/v1/visual-semantic/templates/{semantic_id}")
    async def add_visual_semantic_template(
        request: Request,
        semantic_id: Annotated[str, PathParameter(pattern=r"^[a-z][a-z0-9.-]{2,127}$")],
        file: Annotated[UploadFile, File()],
    ) -> dict[str, Any]:
        """用户编辑/上传图标后，把该图像加入 Reviewed 模板并持久化（保留样式更新）。"""
        service = request.app.state.visual_catalog_service
        image_bytes = await file.read(runtime_settings.max_upload_bytes + 1)
        try:
            profile = await run_in_threadpool(
                service.add_reviewed_template, semantic_id, image_bytes
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"profile": profile}

    @app.get("/v1/visual-semantic/catalog")
    async def get_visual_semantic_catalog(request: Request) -> dict[str, Any]:
        """返回完整资源库目录（匹配配置 + 全部 profile），供前端编辑/回显。"""
        service = request.app.state.visual_catalog_service
        return await run_in_threadpool(service.catalog_mapping)

    @app.put("/v1/visual-semantic/catalog/{semantic_id}")
    async def update_visual_semantic_profile(
        request: Request,
        semantic_id: Annotated[str, PathParameter(pattern=r"^[a-z][a-z0-9.-]{2,127}$")],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """更新某个语义对象的可编辑元数据并持久化（保存后立即作为解析依据）。"""
        service = request.app.state.visual_catalog_service
        try:
            profile = await run_in_threadpool(
                service.update_profile, semantic_id, payload
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="semantic_id not found") from exc
        return {"profile": profile}

    @app.post("/v1/visual-semantic/catalog/reload")
    async def reload_visual_semantic_catalog(request: Request) -> dict[str, Any]:
        """丢弃运行时改动，从包内默认模板重新 seed（误改后回滚/手动同步）。"""
        service = request.app.state.visual_catalog_service
        return await run_in_threadpool(service.reload_from_default)

    @app.get("/v1/visual-semantic/catalog-path")
    async def get_visual_semantic_catalog_path(request: Request) -> dict[str, Any]:
        service = request.app.state.visual_catalog_service
        return {"catalog_path": str(service.catalog_path)}

    return app


app = create_app()
