"""Immutable LessonForge adoption and signed RillML release-index checks."""

from __future__ import annotations

import hashlib
import json
import platform
import re
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from document_intelligence.exceptions import RillUnavailableError

ADOPTION_PATH = Path(__file__).resolve().parents[1] / "defaults" / "rill_adoption.json"
MAX_RELEASE_INDEX_BYTES = 256 * 1024
MAX_RUNTIME_ARTIFACT_BYTES = 128 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AdoptionTrust(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_index: dict[str, str] = Field(alias="releaseIndex")
    model: dict[str, str]
    handler: dict[str, str]

    @field_validator("release_index", "model", "handler")
    @classmethod
    def validate_keys(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("Rill trust store cannot be empty")
        for key_id, public_key in value.items():
            if not key_id or len(key_id) > 96:
                raise ValueError("invalid Rill publisher key id")
            if len(public_key) != 64:
                raise ValueError("Rill Ed25519 public keys must be 32 bytes in hex")
            int(public_key, 16)
        return {key: value.lower() for key, value in value.items()}


class RillAdoptionLock(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    upstream_repository: str = Field(alias="upstreamRepository")
    supported: str
    tested: str
    tag: str
    commit: str
    release_index_schema: int = Field(alias="releaseIndexSchema")
    stable_runtime_api: int = Field(alias="stableRuntimeApi")
    production_protocol: Literal["stable-v2"] = Field(alias="productionProtocol")
    upstream_latest_stable: str = Field(alias="upstreamLatestStable")
    release_index_sha256: str = Field(alias="releaseIndexSha256")
    trust: AdoptionTrust
    qualification: dict[str, str]

    @field_validator("release_index_sha256")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("release index digest must be lowercase SHA-256")
        return value

    @model_validator(mode="after")
    def validate_frozen_identity(self) -> RillAdoptionLock:
        if self.supported != "1.2.0" or self.tested != self.supported:
            raise ValueError("LessonForge only supports and tests the locked RillML 1.2.0")
        if self.tag != "v1.2.0" or self.commit != "dc96fdb3bf55eacdd1c093f1be08d1c9daed4400":
            raise ValueError("RillML adoption identity is not the verified v1.2.0 release")
        if self.release_index_schema != 3 or self.stable_runtime_api != 2:
            raise ValueError("RillML 1.2.0 stable contract is schema 3 / API 2")
        if self.upstream_latest_stable != self.supported:
            raise ValueError("upstream latest stable must equal the qualified stable release")
        return self


class ReleaseArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: Literal["runtime", "model", "handler", "pm-adapter"]
    id: str
    version: str
    runtime_api_version: int = Field(default=0, alias="runtimeApiVersion")
    target_os: str | None = Field(default=None, alias="targetOs")
    target_arch: str | None = Field(default=None, alias="targetArch")
    target_libc: str | None = Field(default=None, alias="targetLibc")
    handler_api_version: int | None = Field(default=None, alias="handlerApiVersion")
    min_runtime_version: str | None = Field(default=None, alias="minRuntimeVersion")
    pm_adapter_protocol_version: int | None = Field(default=None, alias="pmAdapterProtocolVersion")
    url: str
    sha256: str
    size: int

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("release artifact digest must be lowercase SHA-256")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> ReleaseArtifact:
        if not self.id or len(self.id) > 96 or not self.version or len(self.version) > 48:
            raise ValueError("release artifact identity is invalid")
        if self.size <= 0 or self.size > MAX_RUNTIME_ARTIFACT_BYTES:
            raise ValueError("release artifact size is outside the safe bound")
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("release artifact URL must be HTTPS without credentials")
        if self.kind == "runtime":
            if self.id not in {"rill-runtime", "rill-runtime-musl"}:
                raise ValueError("unknown Rill runtime artifact id")
            if self.runtime_api_version != 2 or not self.target_os or not self.target_arch:
                raise ValueError("runtime artifact must declare API, OS and architecture")
            if self.target_os == "linux":
                expected = "musl" if self.id == "rill-runtime-musl" else "gnu"
                if self.target_libc != expected:
                    raise ValueError("Linux runtime libc does not match artifact id")
            elif self.target_libc is not None:
                raise ValueError("non-Linux runtime must not declare libc")
        elif self.kind == "model":
            if self.runtime_api_version != 2 or self.target_os or self.target_arch:
                raise ValueError("model artifact platform/API fields are invalid")
        elif self.kind == "handler":
            if self.runtime_api_version != 2 or self.target_os or self.target_arch:
                raise ValueError("handler artifact platform/API fields are invalid")
            if self.handler_api_version != 1 or not self.min_runtime_version:
                raise ValueError("handler artifact must declare Handler API v1")
        else:
            if self.id != "rill-pm-adapter" or self.runtime_api_version != 0:
                raise ValueError("PM adapter is not a Rill Runtime artifact")
        return self


class ReleaseIndexPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: int = Field(alias="schemaVersion")
    channel: Literal["stable", "candidate"]
    generated_at: str = Field(alias="generatedAt")
    publisher_key_id: str = Field(alias="publisherKeyId")
    artifacts: list[ReleaseArtifact]

    @model_validator(mode="after")
    def validate_shape(self) -> ReleaseIndexPayload:
        if self.schema_version != 3 or self.channel != "stable":
            raise ValueError("LessonForge requires the signed stable release-index schema 3")
        if not self.generated_at or len(self.generated_at) > 64 or not self.artifacts:
            raise ValueError("release index metadata is invalid")
        identities: set[tuple[Any, ...]] = set()
        for artifact in self.artifacts:
            identity = (
                artifact.kind,
                artifact.id,
                artifact.version,
                artifact.target_os,
                artifact.target_arch,
                artifact.target_libc,
            )
            if identity in identities:
                raise ValueError("release index contains duplicate artifact identity")
            identities.add(identity)
        return self


class SignedReleaseIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: ReleaseIndexPayload
    signature: str


class RillDistributionError(RillUnavailableError):
    """A fail-closed distribution error with a machine-readable reason."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


def load_adoption_lock(path: Path = ADOPTION_PATH) -> RillAdoptionLock:
    try:
        with path.open("rb") as handle:
            raw = handle.read(64 * 1024)
        return RillAdoptionLock.model_validate_json(raw)
    except (OSError, ValueError) as exc:
        raise RillDistributionError(
            "RILL_ADOPTION_LOCK_INVALID", "Rill adoption lock is invalid"
        ) from exc


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def parse_and_verify_release_index(
    raw: bytes,
    *,
    lock: RillAdoptionLock | None = None,
) -> SignedReleaseIndex:
    adoption = lock or load_adoption_lock()
    if len(raw) == 0 or len(raw) > MAX_RELEASE_INDEX_BYTES:
        raise RillDistributionError(
            "RILL_INDEX_TOO_LARGE", "signed Rill release index exceeds its limit"
        )
    try:
        index = SignedReleaseIndex.model_validate_json(raw)
    except ValueError as exc:
        raise RillDistributionError(
            "RILL_INDEX_MALFORMED", "signed Rill release index is malformed"
        ) from exc
    if index.payload.publisher_key_id not in adoption.trust.release_index:
        raise RillDistributionError(
            "RILL_INDEX_UNKNOWN_PUBLISHER", "release-index publisher is not trusted"
        )
    if len(index.signature) != 128 or not re.fullmatch(r"[0-9a-f]{128}", index.signature):
        raise RillDistributionError(
            "RILL_INDEX_SIGNATURE_INVALID", "release-index signature encoding is invalid"
        )
    try:
        raw_document = json.loads(raw)
        signed_payload = raw_document["payload"]
        if not isinstance(signed_payload, dict):
            raise ValueError("release-index payload is not an object")
        key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(adoption.trust.release_index[index.payload.publisher_key_id])
        )
        key.verify(bytes.fromhex(index.signature), canonical_json(signed_payload))
    except (InvalidSignature, ValueError) as exc:
        raise RillDistributionError(
            "RILL_INDEX_SIGNATURE_INVALID", "release-index signature is invalid"
        ) from exc
    return index


def verify_locked_release_index(
    raw: bytes,
    *,
    lock: RillAdoptionLock | None = None,
) -> SignedReleaseIndex:
    """Verify one immutable release index against the complete adoption lock.

    Callers must use this boundary instead of composing the lower-level parser
    and identity checks themselves.  The pinned digest is deliberately checked
    before signature and artifact selection so a validly signed index from a
    different immutable release cannot be adopted accidentally.
    """

    adoption = lock or load_adoption_lock()
    if len(raw) == 0 or len(raw) > MAX_RELEASE_INDEX_BYTES:
        raise RillDistributionError(
            "RILL_INDEX_TOO_LARGE", "signed Rill release index exceeds its limit"
        )
    if hashlib.sha256(raw).hexdigest() != adoption.release_index_sha256:
        raise RillDistributionError(
            "RILL_INDEX_DIGEST_MISMATCH",
            "signed Rill release index differs from the immutable adoption lock",
        )
    index = parse_and_verify_release_index(raw, lock=adoption)
    verify_release_index_identity(index, lock=adoption)
    return index


def verify_release_index_identity(
    index: SignedReleaseIndex,
    *,
    lock: RillAdoptionLock | None = None,
) -> None:
    adoption = lock or load_adoption_lock()
    expected_prefix = (
        f"/" f"{adoption.upstream_repository}/releases/download/{adoption.tag}/"
    )
    for artifact in index.payload.artifacts:
        if artifact.version != adoption.supported:
            raise RillDistributionError(
                "RILL_ARTIFACT_VERSION_MISMATCH", "release artifact version is not 1.2.0"
            )
        parsed = urlparse(artifact.url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "github.com"
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.query
            or not parsed.path.startswith(expected_prefix)
            or not parsed.path[len(expected_prefix) :]
            or "/" in parsed.path[len(expected_prefix) :]
        ):
            raise RillDistributionError(
                "RILL_ARTIFACT_URL_MISMATCH", "release artifact is not from the immutable tag"
            )
        if (
            artifact.kind in {"runtime", "model", "handler"}
            and artifact.runtime_api_version != adoption.stable_runtime_api
        ):
            raise RillDistributionError(
                "RILL_ARTIFACT_API_MISMATCH", "release artifact API is not stable v2"
            )


def resolve_target(
    *,
    system: str | None = None,
    machine: str | None = None,
    libc: str | None = None,
) -> tuple[str, str, str | None]:
    raw_system = (system or platform.system()).lower()
    target_os = {
        "darwin": "macos",
        "windows": "windows",
        "linux": "linux",
        "freebsd": "freebsd",
    }.get(raw_system)
    if target_os is None:
        raise RillDistributionError(
            "RILL_UNSUPPORTED_PLATFORM", "Rill runtime platform is unsupported"
        )
    raw_machine = (machine or platform.machine()).lower().replace("-", "_")
    target_arch = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
        "armv7l": "armv7",
        "armv7": "armv7",
        "riscv64": "riscv64",
        "s390x": "s390x",
        "ppc64le": "powerpc64le",
        "powerpc64le": "powerpc64le",
        "loongarch64": "loongarch64",
    }.get(raw_machine)
    if target_arch is None:
        raise RillDistributionError(
            "RILL_UNSUPPORTED_ARCH", "Rill runtime architecture is unsupported"
        )
    if target_os != "linux":
        return target_os, target_arch, None
    detected = (libc or platform.libc_ver()[0]).lower()
    if "musl" in detected:
        return target_os, target_arch, "musl"
    if detected in {"glibc", "libc", "gnu"} or "glibc" in detected:
        return target_os, target_arch, "gnu"
    raise RillDistributionError("RILL_UNSUPPORTED_LIBC", "Linux libc could not be resolved safely")


def select_runtime(
    index: SignedReleaseIndex,
    *,
    target: tuple[str, str, str | None] | None = None,
    lock: RillAdoptionLock | None = None,
) -> ReleaseArtifact:
    adoption = lock or load_adoption_lock()
    target_value = target or resolve_target()
    matches = [
        artifact
        for artifact in index.payload.artifacts
        if artifact.kind == "runtime"
        and artifact.version == adoption.supported
        and (artifact.target_os, artifact.target_arch, artifact.target_libc) == target_value
    ]
    if len(matches) != 1:
        raise RillDistributionError(
            "RILL_TARGET_NOT_FOUND", "no unique verified Rill runtime matches this target"
        )
    return matches[0]


def verify_artifact_bytes(data: bytes, artifact: ReleaseArtifact) -> None:
    if len(data) != artifact.size:
        raise RillDistributionError(
            "RILL_ARTIFACT_SIZE_MISMATCH", "downloaded Rill artifact size differs from the index"
        )
    if hashlib.sha256(data).hexdigest() != artifact.sha256:
        raise RillDistributionError(
            "RILL_ARTIFACT_SHA256_MISMATCH",
            "downloaded Rill artifact digest differs from the index",
        )


def verify_artifact_file(path: Path, artifact: ReleaseArtifact) -> None:
    if path.is_symlink() or not path.is_file():
        raise RillDistributionError(
            "RILL_ARTIFACT_FILE_INVALID", "Rill artifact path is not a regular file"
        )
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            if size > artifact.size:
                raise RillDistributionError(
                    "RILL_ARTIFACT_SIZE_MISMATCH", "Rill artifact exceeds its indexed size"
                )
            digest.update(chunk)
    if size != artifact.size:
        raise RillDistributionError(
            "RILL_ARTIFACT_SIZE_MISMATCH", "Rill artifact file size differs from the index"
        )
    if digest.hexdigest() != artifact.sha256:
        raise RillDistributionError(
            "RILL_ARTIFACT_SHA256_MISMATCH", "Rill artifact file digest differs from the index"
        )


def lock_for_runtime() -> RillAdoptionLock:
    """Load the one packaged adoption lock; exposed for API and Web status."""

    return load_adoption_lock()
