from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_PACKAGE_DEFAULT_PARSER_CONFIG = Path(__file__).resolve().parent / "defaults" / "parsers.yaml"


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_profile: Literal["development", "production", "test"] = "development"
    workspace: Path = Field(default=Path("./var"))
    api_tenant_tokens_sha256: dict[str, str] = Field(default_factory=dict)
    api_requests_per_minute: int = Field(default=120, ge=1, le=100000)
    api_max_concurrent_requests_per_tenant: int = Field(default=4, ge=1, le=1024)
    # 教材 PDF 大体积（127MB+）解析实测约 160s，默认 120s 会误杀整书/多页解析请求。
    api_request_timeout_seconds: float = Field(default=600.0, gt=0.0, le=3600.0)
    metrics_access_token_sha256: str | None = None
    single_node_mode: bool = True
    pdf_render_backend: Literal["disabled", "pymupdf"] = "pymupdf"
    pymupdf_license_resolved: bool = False
    # 教材 PDF 扫描件可达 100MB+（实测 2025 苏教版三年级上册 127.5MB），
    # 默认上传上限需覆盖真实教材，否则整书解析/分页上传会被 INPUT_CORRUPT 拒绝。
    max_upload_bytes: int = Field(default=256 * 1024 * 1024, gt=0)
    max_pdf_pages: int = Field(default=2000, gt=0, le=10000)
    max_page_elements: int = Field(default=20000, gt=0)
    max_document_elements: int = Field(default=200000, gt=0)
    max_binary_artifact_bytes: int = Field(default=200 * 1024 * 1024, gt=0)
    max_render_pixels: int = Field(default=50_000_000, gt=0)
    parser_config: Path = Field(default=_PACKAGE_DEFAULT_PARSER_CONFIG)
    default_parser: str = "auto"
    enable_standard_writes: bool = False
    standard_access_token_sha256: str | None = None
    match_high_threshold: float = Field(default=0.86, ge=0.0, le=1.0)
    match_local_threshold: float = Field(default=0.78, ge=0.0, le=1.0)
    match_min_margin: float = Field(default=0.08, ge=0.0, le=1.0)
    match_min_local_inliers: int = Field(default=10, ge=4)
    structure_max_columns: int = Field(default=4, ge=1, le=8)
    structure_spanning_width: float = Field(default=0.70, ge=0.40, le=1.0)
    structure_column_gap: float = Field(default=0.18, ge=0.05, le=0.50)
    structure_repeated_margin_ratio: float = Field(default=0.60, ge=0.40, le=1.0)
    structure_caption_threshold: float = Field(default=0.70, ge=0.50, le=1.0)
    structure_cross_page_threshold: float = Field(default=0.70, ge=0.50, le=1.0)
    enable_domain_pack_writes: bool = False
    domain_pack_access_token_sha256: str | None = None
    domain_pack_require_signatures: bool = False
    domain_pack_trusted_public_keys: dict[str, str] = Field(default_factory=dict)
    domain_pack_max_archive_files: int = Field(default=2000, gt=0, le=10000)
    domain_pack_max_archive_bytes: int = Field(default=128 * 1024 * 1024, gt=0)
    domain_pack_max_compression_ratio: float = Field(default=100.0, gt=1.0, le=1000.0)
    enable_family_detection_writes: bool = False
    family_detection_access_token_sha256: str | None = None
    family_detection_max_profiles: int = Field(default=64, ge=1, le=256)
    rill_shadow_backend: Literal[
        "disabled", "stable-v2", "subprocess", "preview-v3", "reference"
    ] = "disabled"
    rill_runtime_command: tuple[str, ...] | None = None
    rill_evaluate_capability: str = "org.lessonforge.shadow.evaluate"
    # Stable v2 has no stateful feedback operation. Feedback is Host-owned by
    # default; an explicit capability is reserved for a separately qualified
    # consumer handler and is never inferred.
    rill_feedback_capability: str | None = None
    rill_runtime_artifact_sha256: str | None = None
    rill_model_artifact_sha256: str | None = None
    rill_handler_artifact_sha256: str | None = None
    rill_allow_unmanaged_stable_v2: bool = False
    rill_access_token_sha256: str | None = None
    enable_rill_shadow_writes: bool = False
    rill_reference_backend_allowed: bool = False
    rill_request_timeout_seconds: float = Field(default=5.0, gt=0.0, le=120.0)
    rill_startup_timeout_seconds: float = Field(default=5.0, gt=0.0, le=120.0)
    rill_max_message_bytes: int = Field(default=1024 * 1024, gt=0, le=1024 * 1024)
    rill_drift_min_samples: int = Field(default=20, ge=5, le=100000)
    rill_drift_threshold: float = Field(default=5.0, gt=0.0, le=1000.0)
    rill_drift_delta: float = Field(default=0.01, ge=0.0, le=1.0)
    enable_rill_assist_writes: bool = False
    enable_rill_assist_execution: bool = False
    rill_assist_access_token_sha256: str | None = None
    rill_assist_min_expert_feedback: int = Field(default=30, ge=1, le=1000000)
    rill_assist_min_production_like_feedback: int = Field(default=30, ge=1, le=1000000)
    rill_assist_min_accuracy: float = Field(default=0.90, ge=0.0, le=1.0)
    rill_assist_min_action_feedback: int = Field(default=5, ge=1, le=1000000)
    rill_assist_qualification_ttl_hours: int = Field(default=168, ge=1, le=8760)
    enable_mlops_writes: bool = False
    enable_mlops_release: bool = False
    mlops_access_token_sha256: str | None = None
    mlops_minimum_accuracy: float = Field(default=0.90, ge=0.0, le=1.0)
    mlops_minimum_challenge_improvement: float = Field(default=0.001, ge=0.0, le=1.0)
    mlops_maximum_latency_ms_p95: float = Field(default=30000.0, gt=0.0)
    mlops_maximum_cost_usd_per_document: float = Field(default=10.0, ge=0.0)
    mlops_maximum_family_regression: float = Field(default=0.02, ge=0.0, le=1.0)
    mlops_minimum_shadow_samples: int = Field(default=100, ge=1, le=100000000)
    enable_production_qualification_writes: bool = False
    production_qualification_access_token_sha256: str | None = None
    production_minimum_domains: int = Field(default=3, ge=1, le=64)
    production_minimum_gold_documents: int = Field(default=100, ge=1)
    production_minimum_challenge_documents: int = Field(default=50, ge=1)
    production_minimum_parser_accuracy: float = Field(default=0.90, ge=0.0, le=1.0)
    production_maximum_parser_timeout_rate: float = Field(default=0.01, ge=0.0, le=1.0)
    production_maximum_parser_failure_rate: float = Field(default=0.01, ge=0.0, le=1.0)
    production_minimum_deterministic_replay_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    production_minimum_soak_hours: float = Field(default=168.0, gt=0.0)
    production_minimum_scale_concurrency: int = Field(default=8, ge=1)
    production_minimum_scale_documents: int = Field(default=10000, ge=1)
    production_maximum_scale_error_rate: float = Field(default=0.01, ge=0.0, le=1.0)
    production_minimum_branch_coverage: float = Field(default=80.0, ge=0.0, le=100.0)
    production_minimum_pilot_days: float = Field(default=7.0, gt=0.0)
    production_minimum_pilot_documents: int = Field(default=500, ge=1)
    production_minimum_pilot_expert_reviews: int = Field(default=100, ge=1)
    production_minimum_pilot_accuracy: float = Field(default=0.90, ge=0.0, le=1.0)
    enable_qualification_campaign_writes: bool = False
    qualification_campaign_access_token_sha256: str | None = None
    qualification_campaign_maximum_lease_seconds: int = Field(default=86400, ge=30, le=604800)
    qualification_campaign_max_bundle_bytes: int = Field(
        default=32 * 1024 * 1024, ge=1024, le=512 * 1024 * 1024
    )

    @classmethod
    def from_env(cls) -> Settings:
        parser_config_env = os.getenv("DI_PARSER_CONFIG")
        return cls(
            deployment_profile=os.getenv("DI_DEPLOYMENT_PROFILE", "development"),
            workspace=Path(os.getenv("DI_WORKSPACE", "./var")),
            api_tenant_tokens_sha256=json.loads(
                os.getenv("DI_API_TENANT_TOKENS_SHA256_JSON", "{}")
            ),
            api_requests_per_minute=int(os.getenv("DI_API_REQUESTS_PER_MINUTE", "120")),
            api_max_concurrent_requests_per_tenant=int(
                os.getenv("DI_API_MAX_CONCURRENT_REQUESTS_PER_TENANT", "4")
            ),
            api_request_timeout_seconds=float(
                os.getenv("DI_API_REQUEST_TIMEOUT_SECONDS", "600")
            ),
            metrics_access_token_sha256=(
                os.getenv("DI_METRICS_ACCESS_TOKEN_SHA256") or None
            ),
            single_node_mode=os.getenv("DI_SINGLE_NODE_MODE", "true").lower()
            in {"1", "true", "yes", "on"},
            pdf_render_backend=os.getenv("DI_PDF_RENDER_BACKEND", "pymupdf"),
            pymupdf_license_resolved=os.getenv(
                "DI_PYMUPDF_LICENSE_RESOLVED", "false"
            ).lower() in {"1", "true", "yes", "on"},
            max_upload_bytes=int(os.getenv("DI_MAX_UPLOAD_BYTES", str(256 * 1024 * 1024))),
            max_pdf_pages=int(os.getenv("DI_MAX_PDF_PAGES", "2000")),
            max_page_elements=int(os.getenv("DI_MAX_PAGE_ELEMENTS", "20000")),
            max_document_elements=int(os.getenv("DI_MAX_DOCUMENT_ELEMENTS", "200000")),
            max_binary_artifact_bytes=int(
                os.getenv("DI_MAX_BINARY_ARTIFACT_BYTES", str(200 * 1024 * 1024))
            ),
            max_render_pixels=int(os.getenv("DI_MAX_RENDER_PIXELS", "50000000")),
            parser_config=(
                Path(parser_config_env)
                if parser_config_env
                else _PACKAGE_DEFAULT_PARSER_CONFIG
            ),
            default_parser=os.getenv("DI_DEFAULT_PARSER", "auto"),
            enable_standard_writes=os.getenv("DI_ENABLE_STANDARD_WRITES", "false").lower()
            in {"1", "true", "yes", "on"},
            standard_access_token_sha256=(
                os.getenv("DI_STANDARD_ACCESS_TOKEN_SHA256") or None
            ),
            match_high_threshold=float(os.getenv("DI_MATCH_HIGH_THRESHOLD", "0.86")),
            match_local_threshold=float(os.getenv("DI_MATCH_LOCAL_THRESHOLD", "0.78")),
            match_min_margin=float(os.getenv("DI_MATCH_MIN_MARGIN", "0.08")),
            match_min_local_inliers=int(os.getenv("DI_MATCH_MIN_LOCAL_INLIERS", "10")),
            structure_max_columns=int(os.getenv("DI_STRUCTURE_MAX_COLUMNS", "4")),
            structure_spanning_width=float(
                os.getenv("DI_STRUCTURE_SPANNING_WIDTH", "0.70")
            ),
            structure_column_gap=float(os.getenv("DI_STRUCTURE_COLUMN_GAP", "0.18")),
            structure_repeated_margin_ratio=float(
                os.getenv("DI_STRUCTURE_REPEATED_MARGIN_RATIO", "0.60")
            ),
            structure_caption_threshold=float(
                os.getenv("DI_STRUCTURE_CAPTION_THRESHOLD", "0.70")
            ),
            structure_cross_page_threshold=float(
                os.getenv("DI_STRUCTURE_CROSS_PAGE_THRESHOLD", "0.70")
            ),
            enable_domain_pack_writes=os.getenv(
                "DI_ENABLE_DOMAIN_PACK_WRITES", "false"
            ).lower() in {"1", "true", "yes", "on"},
            domain_pack_access_token_sha256=(
                os.getenv("DI_DOMAIN_PACK_ACCESS_TOKEN_SHA256") or None
            ),
            domain_pack_require_signatures=os.getenv(
                "DI_DOMAIN_PACK_REQUIRE_SIGNATURES", "false"
            ).lower() in {"1", "true", "yes", "on"},
            domain_pack_trusted_public_keys=json.loads(
                os.getenv("DI_DOMAIN_PACK_TRUSTED_KEYS_JSON", "{}")
            ),
            domain_pack_max_archive_files=int(
                os.getenv("DI_DOMAIN_PACK_MAX_ARCHIVE_FILES", "2000")
            ),
            domain_pack_max_archive_bytes=int(
                os.getenv("DI_DOMAIN_PACK_MAX_ARCHIVE_BYTES", str(128 * 1024 * 1024))
            ),
            domain_pack_max_compression_ratio=float(
                os.getenv("DI_DOMAIN_PACK_MAX_COMPRESSION_RATIO", "100")
            ),
            enable_family_detection_writes=os.getenv(
                "DI_ENABLE_FAMILY_DETECTION_WRITES", "false"
            ).lower() in {"1", "true", "yes", "on"},
            family_detection_access_token_sha256=(
                os.getenv("DI_FAMILY_DETECTION_ACCESS_TOKEN_SHA256") or None
            ),
            family_detection_max_profiles=int(
                os.getenv("DI_FAMILY_DETECTION_MAX_PROFILES", "64")
            ),
            rill_shadow_backend=os.getenv("DI_RILL_SHADOW_BACKEND", "disabled"),
            rill_runtime_command=cls._parse_command(
                os.getenv("DI_RILL_RUNTIME_COMMAND_JSON")
            ),
            rill_evaluate_capability=os.getenv(
                "DI_RILL_EVALUATE_CAPABILITY", "org.lessonforge.shadow.evaluate"
            ),
            rill_feedback_capability=(
                os.getenv("DI_RILL_FEEDBACK_CAPABILITY", "")
                or None
            ),
            rill_runtime_artifact_sha256=(
                os.getenv("DI_RILL_RUNTIME_ARTIFACT_SHA256") or None
            ),
            rill_model_artifact_sha256=(
                os.getenv("DI_RILL_MODEL_ARTIFACT_SHA256") or None
            ),
            rill_handler_artifact_sha256=(
                os.getenv("DI_RILL_HANDLER_ARTIFACT_SHA256") or None
            ),
            rill_allow_unmanaged_stable_v2=os.getenv(
                "DI_RILL_ALLOW_UNMANAGED_STABLE_V2", "false"
            ).lower()
            in {"1", "true", "yes", "on"},
            rill_access_token_sha256=(os.getenv("DI_RILL_ACCESS_TOKEN_SHA256") or None),
            enable_rill_shadow_writes=os.getenv(
                "DI_ENABLE_RILL_SHADOW_WRITES", "false"
            ).lower() in {"1", "true", "yes", "on"},
            rill_reference_backend_allowed=os.getenv(
                "DI_RILL_REFERENCE_BACKEND_ALLOWED", "false"
            ).lower() in {"1", "true", "yes", "on"},
            rill_request_timeout_seconds=float(
                os.getenv("DI_RILL_REQUEST_TIMEOUT_SECONDS", "5")
            ),
            rill_startup_timeout_seconds=float(
                os.getenv("DI_RILL_STARTUP_TIMEOUT_SECONDS", "5")
            ),
            rill_max_message_bytes=int(
                os.getenv("DI_RILL_MAX_MESSAGE_BYTES", str(1024 * 1024))
            ),
            rill_drift_min_samples=int(os.getenv("DI_RILL_DRIFT_MIN_SAMPLES", "20")),
            rill_drift_threshold=float(os.getenv("DI_RILL_DRIFT_THRESHOLD", "5")),
            rill_drift_delta=float(os.getenv("DI_RILL_DRIFT_DELTA", "0.01")),
            enable_rill_assist_writes=os.getenv(
                "DI_ENABLE_RILL_ASSIST_WRITES", "false"
            ).lower() in {"1", "true", "yes", "on"},
            enable_rill_assist_execution=os.getenv(
                "DI_ENABLE_RILL_ASSIST_EXECUTION", "false"
            ).lower() in {"1", "true", "yes", "on"},
            rill_assist_access_token_sha256=(
                os.getenv("DI_RILL_ASSIST_ACCESS_TOKEN_SHA256") or None
            ),
            rill_assist_min_expert_feedback=int(
                os.getenv("DI_RILL_ASSIST_MIN_EXPERT_FEEDBACK", "30")
            ),
            rill_assist_min_production_like_feedback=int(
                os.getenv("DI_RILL_ASSIST_MIN_PRODUCTION_LIKE_FEEDBACK", "30")
            ),
            rill_assist_min_accuracy=float(
                os.getenv("DI_RILL_ASSIST_MIN_ACCURACY", "0.90")
            ),
            rill_assist_min_action_feedback=int(
                os.getenv("DI_RILL_ASSIST_MIN_ACTION_FEEDBACK", "5")
            ),
            rill_assist_qualification_ttl_hours=int(
                os.getenv("DI_RILL_ASSIST_QUALIFICATION_TTL_HOURS", "168")
            ),
            enable_mlops_writes=os.getenv("DI_ENABLE_MLOPS_WRITES", "false").lower()
            in {"1", "true", "yes", "on"},
            enable_mlops_release=os.getenv("DI_ENABLE_MLOPS_RELEASE", "false").lower()
            in {"1", "true", "yes", "on"},
            mlops_access_token_sha256=(os.getenv("DI_MLOPS_ACCESS_TOKEN_SHA256") or None),
            mlops_minimum_accuracy=float(os.getenv("DI_MLOPS_MINIMUM_ACCURACY", "0.90")),
            mlops_minimum_challenge_improvement=float(
                os.getenv("DI_MLOPS_MINIMUM_CHALLENGE_IMPROVEMENT", "0.001")
            ),
            mlops_maximum_latency_ms_p95=float(
                os.getenv("DI_MLOPS_MAXIMUM_LATENCY_MS_P95", "30000")
            ),
            mlops_maximum_cost_usd_per_document=float(
                os.getenv("DI_MLOPS_MAXIMUM_COST_USD_PER_DOCUMENT", "10")
            ),
            mlops_maximum_family_regression=float(
                os.getenv("DI_MLOPS_MAXIMUM_FAMILY_REGRESSION", "0.02")
            ),
            mlops_minimum_shadow_samples=int(
                os.getenv("DI_MLOPS_MINIMUM_SHADOW_SAMPLES", "100")
            ),
            enable_production_qualification_writes=os.getenv(
                "DI_ENABLE_PRODUCTION_QUALIFICATION_WRITES", "false"
            ).lower() in {"1", "true", "yes", "on"},
            production_qualification_access_token_sha256=(
                os.getenv("DI_PRODUCTION_QUALIFICATION_ACCESS_TOKEN_SHA256") or None
            ),
            production_minimum_domains=int(os.getenv("DI_PRODUCTION_MINIMUM_DOMAINS", "3")),
            production_minimum_gold_documents=int(
                os.getenv("DI_PRODUCTION_MINIMUM_GOLD_DOCUMENTS", "100")
            ),
            production_minimum_challenge_documents=int(
                os.getenv("DI_PRODUCTION_MINIMUM_CHALLENGE_DOCUMENTS", "50")
            ),
            production_minimum_parser_accuracy=float(
                os.getenv("DI_PRODUCTION_MINIMUM_PARSER_ACCURACY", "0.90")
            ),
            production_maximum_parser_timeout_rate=float(
                os.getenv("DI_PRODUCTION_MAXIMUM_PARSER_TIMEOUT_RATE", "0.01")
            ),
            production_maximum_parser_failure_rate=float(
                os.getenv("DI_PRODUCTION_MAXIMUM_PARSER_FAILURE_RATE", "0.01")
            ),
            production_minimum_deterministic_replay_rate=float(
                os.getenv("DI_PRODUCTION_MINIMUM_DETERMINISTIC_REPLAY_RATE", "1.0")
            ),
            production_minimum_soak_hours=float(
                os.getenv("DI_PRODUCTION_MINIMUM_SOAK_HOURS", "168")
            ),
            production_minimum_scale_concurrency=int(
                os.getenv("DI_PRODUCTION_MINIMUM_SCALE_CONCURRENCY", "8")
            ),
            production_minimum_scale_documents=int(
                os.getenv("DI_PRODUCTION_MINIMUM_SCALE_DOCUMENTS", "10000")
            ),
            production_maximum_scale_error_rate=float(
                os.getenv("DI_PRODUCTION_MAXIMUM_SCALE_ERROR_RATE", "0.01")
            ),
            production_minimum_branch_coverage=float(
                os.getenv("DI_PRODUCTION_MINIMUM_BRANCH_COVERAGE", "80")
            ),
            production_minimum_pilot_days=float(
                os.getenv("DI_PRODUCTION_MINIMUM_PILOT_DAYS", "7")
            ),
            production_minimum_pilot_documents=int(
                os.getenv("DI_PRODUCTION_MINIMUM_PILOT_DOCUMENTS", "500")
            ),
            production_minimum_pilot_expert_reviews=int(
                os.getenv("DI_PRODUCTION_MINIMUM_PILOT_EXPERT_REVIEWS", "100")
            ),
            production_minimum_pilot_accuracy=float(
                os.getenv("DI_PRODUCTION_MINIMUM_PILOT_ACCURACY", "0.90")
            ),
            enable_qualification_campaign_writes=os.getenv(
                "DI_ENABLE_QUALIFICATION_CAMPAIGN_WRITES", "false"
            ).lower() in {"1", "true", "yes", "on"},
            qualification_campaign_access_token_sha256=(
                os.getenv("DI_QUALIFICATION_CAMPAIGN_ACCESS_TOKEN_SHA256") or None
            ),
            qualification_campaign_maximum_lease_seconds=int(
                os.getenv("DI_QUALIFICATION_CAMPAIGN_MAXIMUM_LEASE_SECONDS", "86400")
            ),
            qualification_campaign_max_bundle_bytes=int(
                os.getenv(
                    "DI_QUALIFICATION_CAMPAIGN_MAX_BUNDLE_BYTES",
                    str(32 * 1024 * 1024),
                )
            ),
        )

    @staticmethod
    def _parse_command(value: str | None) -> tuple[str, ...] | None:
        if value is None or not value.strip():
            return None
        parsed = json.loads(value)
        if not isinstance(parsed, list) or not parsed or not all(
            isinstance(item, str) and item and "\x00" not in item for item in parsed
        ):
            raise ValueError("DI_RILL_RUNTIME_COMMAND_JSON must be a non-empty JSON string list")
        return tuple(parsed)

    @field_validator(
        "metrics_access_token_sha256",
        "standard_access_token_sha256",
        "domain_pack_access_token_sha256",
        "family_detection_access_token_sha256",
        "rill_access_token_sha256",
        "rill_assist_access_token_sha256",
        "mlops_access_token_sha256",
        "production_qualification_access_token_sha256",
        "qualification_campaign_access_token_sha256",
        "rill_runtime_artifact_sha256",
        "rill_model_artifact_sha256",
        "rill_handler_artifact_sha256",
    )
    @classmethod
    def validate_standard_access_token_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("access token digest must be a lowercase SHA-256")
        return normalized

    @field_validator("api_tenant_tokens_sha256")
    @classmethod
    def validate_api_tenant_tokens(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for tenant, digest in value.items():
            if not isinstance(tenant, str) or not tenant or len(tenant) > 63:
                raise ValueError("invalid API tenant id")
            if not tenant[0].isalpha() or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
                for character in tenant.lower()
            ):
                raise ValueError("invalid API tenant id")
            if not isinstance(digest, str):
                raise ValueError("tenant API token digest must be a string")
            candidate = digest.strip().lower()
            if len(candidate) != 64 or any(
                character not in "0123456789abcdef" for character in candidate
            ):
                raise ValueError("tenant API token digest must be a lowercase SHA-256")
            normalized[tenant.lower()] = candidate
        return normalized

    @model_validator(mode="after")
    def validate_deployment_profile(self) -> "Settings":
        if self.deployment_profile != "production":
            return self
        if not self.single_node_mode:
            raise ValueError("1.0.x release candidates support only single-node mode")
        if not self.workspace.is_absolute():
            raise ValueError("production workspace must be an absolute path")
        if not self.api_tenant_tokens_sha256:
            raise ValueError("production requires DI_API_TENANT_TOKENS_SHA256_JSON")
        if self.rill_reference_backend_allowed:
            raise ValueError("reference Rill backend is forbidden in production")
        if self.rill_shadow_backend == "preview-v3":
            raise ValueError("Preview IPC v3 is forbidden as the LessonForge production backend")
        if self.rill_feedback_capability is not None:
            raise ValueError(
                "production Stable v2 feedback is Host-owned; configure no Runtime update capability"
            )
        if self.pdf_render_backend == "pymupdf" and not self.pymupdf_license_resolved:
            raise ValueError(
                "PyMuPDF rendering requires an explicit resolved license attestation"
            )
        gated_tokens = [
            (self.enable_standard_writes, self.standard_access_token_sha256, "standard"),
            (self.enable_domain_pack_writes, self.domain_pack_access_token_sha256, "domain"),
            (
                self.enable_family_detection_writes,
                self.family_detection_access_token_sha256,
                "family detection",
            ),
            (self.enable_rill_shadow_writes, self.rill_access_token_sha256, "Rill Shadow"),
            (self.enable_rill_assist_writes, self.rill_assist_access_token_sha256, "Rill Assist"),
            (self.enable_mlops_writes, self.mlops_access_token_sha256, "MLOps"),
            (
                self.enable_production_qualification_writes,
                self.production_qualification_access_token_sha256,
                "production qualification",
            ),
            (
                self.enable_qualification_campaign_writes,
                self.qualification_campaign_access_token_sha256,
                "qualification campaign",
            ),
        ]
        missing = [name for enabled, token, name in gated_tokens if enabled and token is None]
        if missing:
            raise ValueError(
                "production write domains require token digests: " + ", ".join(missing)
            )
        return self

    @property
    def production_mode(self) -> bool:
        return self.deployment_profile == "production"

    @field_validator("parser_config")
    @classmethod
    def parser_config_exists(cls, value: Path) -> Path:
        if not value.is_file():
            raise ValueError(f"parser config does not exist: {value}")
        return value

    @field_validator("rill_evaluate_capability", "rill_feedback_capability")
    @classmethod
    def validate_rill_capability(cls, value: str | None) -> str | None:
        if value is not None and (not value or len(value) > 96):
            raise ValueError("Rill capability must be a bounded non-empty string")
        return value


class ParserConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    kind: str
    expected_version: str
    priority: int = 100
    required_artifact_sha256: str | None = None
    endpoint_env: str | None = None
    health_path: str = "/healthz"
    parse_path: str = "/v1/parse"
    benchmark_only: bool = False
    max_response_bytes: int = Field(default=64 * 1024 * 1024, gt=0)
    health_timeout_seconds: float = Field(default=5.0, gt=0)
    parse_timeout_seconds: float = Field(default=120.0, gt=0)
    notes: str | None = None

    def endpoint(self) -> str | None:
        if not self.endpoint_env:
            return None
        value = os.getenv(self.endpoint_env)
        return value.rstrip("/") if value else None


class ParserConfigFile(BaseModel):
    version: int
    parsers: dict[str, ParserConfig]


def load_parser_config(path: Path) -> ParserConfigFile:
    with path.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] = yaml.safe_load(handle)
    return ParserConfigFile.model_validate(data)
