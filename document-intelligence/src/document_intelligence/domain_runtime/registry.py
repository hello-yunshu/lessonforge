from __future__ import annotations

import base64
import errno
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field

from document_intelligence.domain_pack_sdk import (
    DomainPackManifest,
    LoadedDomainPack,
    load_domain_pack,
)
from document_intelligence.exceptions import (
    DomainPackArchiveError,
    DomainPackCompatibilityError,
    DomainPackConflictError,
    DomainPackSignatureError,
    DomainPackStoreCorruptError,
)
from document_intelligence.schema import SCHEMA_VERSION, SHA256_PATTERN, validate_safe_id


class BuiltinDomainPackRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id: str
    version: str
    content_digest: str = Field(pattern=SHA256_PATTERN)
    has_family_profile: bool = False
    family_id: str | None = None
    capabilities: list[str] = Field(default_factory=list)


class DomainPackRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id: str
    version: str
    content_digest: str = Field(pattern=SHA256_PATTERN)
    installed_at: float = Field(ge=0)
    active: bool = False
    signature_verified: bool = False
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    has_family_profile: bool = False
    family_id: str | None = None


class DomainPackRegistry:
    def __init__(
        self,
        workspace: Path,
        *,
        engine_version: str,
        require_signatures: bool = False,
        trusted_public_keys: dict[str, str] | None = None,
        max_archive_files: int = 2000,
        max_archive_bytes: int = 128 * 1024 * 1024,
        max_compression_ratio: float = 100.0,
    ) -> None:
        self.workspace = workspace
        self.root = workspace / "domain-packs"
        self.packs_dir = self.root / "packs"
        self.state_path = self.root / "state.json"
        self.lock_path = self.root / ".registry.lock"
        if self.root.is_symlink() or self.packs_dir.is_symlink():
            raise ValueError("domain pack namespaces cannot be symlinks")
        self.packs_dir.mkdir(parents=True, exist_ok=True)
        self.engine_version = engine_version
        self.require_signatures = require_signatures
        self.trusted_public_keys = trusted_public_keys or {}
        self.max_archive_files = max_archive_files
        self.max_archive_bytes = max_archive_bytes
        self.max_compression_ratio = max_compression_ratio
        self.builtin_root = Path(__file__).resolve().parents[1] / "defaults" / "domain_packs"

    def install_archive(self, archive: bytes) -> DomainPackRecord:
        if len(archive) > self.max_archive_bytes:
            raise DomainPackArchiveError("domain pack archive exceeds configured size limit")
        with self._lock():
            temp_root = Path(tempfile.mkdtemp(prefix=".install.", dir=self.root))
            try:
                pack_root = self._extract_archive(archive, temp_root)
                manifest = self._load_manifest(pack_root)
                signature_verified = self._verify_signature(manifest)
                pack = load_domain_pack(pack_root, signature_verified=signature_verified)
                self._assert_compatible(pack.manifest)
                final_dir = self._pack_dir(pack.manifest.id, pack.manifest.version)
                if final_dir.exists():
                    existing = self._read_installed(pack.manifest.id, pack.manifest.version)
                    if existing.content_digest != pack.content_digest:
                        raise DomainPackConflictError(
                            "same domain pack ID and version already contains different content"
                        )
                    return self._record(existing)
                final_dir.parent.mkdir(parents=True, exist_ok=True)
                staged = temp_root / ".staged"
                os.rename(pack_root, staged)
                try:
                    os.rename(staged, final_dir)
                except OSError as exc:
                    if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY} and not final_dir.exists():
                        raise
                    if staged.exists():
                        shutil.rmtree(staged)
                    existing = self._read_installed(pack.manifest.id, pack.manifest.version)
                    if existing.content_digest != pack.content_digest:
                        raise DomainPackConflictError(
                            "concurrent domain pack install produced different content"
                        ) from exc
                metadata = {
                    "version": 1,
                    "pack_id": pack.manifest.id,
                    "pack_version": pack.manifest.version,
                    "content_digest": pack.content_digest,
                    "signature_verified": signature_verified,
                    "installed_at": time.time(),
                }
                self._atomic_json(final_dir / ".installed.json", metadata)
                return self._record(self._read_installed(pack.manifest.id, pack.manifest.version))
            finally:
                if temp_root.exists():
                    shutil.rmtree(temp_root)

    def list_builtin_records(self) -> list[BuiltinDomainPackRecord]:
        records: list[BuiltinDomainPackRecord] = []
        if not self.builtin_root.is_dir() or self.builtin_root.is_symlink():
            return records
        for root in sorted(self.builtin_root.iterdir()):
            if not root.is_dir() or root.is_symlink():
                continue
            pack = load_domain_pack(root, signature_verified=False)
            self._assert_compatible(pack.manifest)
            records.append(
                BuiltinDomainPackRecord(
                    pack_id=pack.manifest.id,
                    version=pack.manifest.version,
                    content_digest=pack.content_digest,
                    has_family_profile=pack.family is not None,
                    family_id=pack.family.family_id if pack.family else None,
                    capabilities=pack.manifest.capabilities,
                )
            )
        return records

    def install_builtin(self, pack_id: str) -> DomainPackRecord:
        validate_safe_id(pack_id, field_name="pack_id")
        root = (self.builtin_root / pack_id).resolve()
        builtin = self.builtin_root.resolve()
        if builtin not in root.parents or not root.is_dir() or root.is_symlink():
            raise FileNotFoundError(f"unknown built-in domain pack: {pack_id}")
        return self.install_directory(root)

    def install_directory(self, source: Path) -> DomainPackRecord:
        source = source.resolve()
        if not source.is_dir() or source.is_symlink():
            raise DomainPackArchiveError("domain pack source directory is missing or unsafe")
        fd, archive_name = tempfile.mkstemp(prefix="domain-pack-", suffix=".zip")
        os.close(fd)
        archive_path = Path(archive_name)
        try:
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as target:
                for path in sorted(source.rglob("*")):
                    if path.is_symlink():
                        raise DomainPackArchiveError("domain pack source cannot contain symlinks")
                    if path.is_file():
                        target.write(path, path.relative_to(source).as_posix())
            return self.install_archive(archive_path.read_bytes())
        finally:
            archive_path.unlink(missing_ok=True)

    def activate(self, pack_id: str, version: str) -> DomainPackRecord:
        pack = self._read_installed(pack_id, version)
        self._assert_compatible(pack.manifest)
        with self._lock():
            state = self._read_state()
            state["active"][pack_id] = version
            self._atomic_json(self.state_path, state)
        return self._record(pack, active=True)

    def deactivate(self, pack_id: str) -> None:
        validate_safe_id(pack_id, field_name="pack_id")
        with self._lock():
            state = self._read_state()
            state["active"].pop(pack_id, None)
            self._atomic_json(self.state_path, state)

    def uninstall(self, pack_id: str, version: str) -> None:
        with self._lock():
            self._read_installed(pack_id, version, enforce_compatibility=False)
            state = self._read_state()
            if state["active"].get(pack_id) == version:
                raise DomainPackConflictError(
                    "active domain pack version must be deactivated first"
                )
            references = self._domain_result_references(pack_id, version)
            if references:
                raise DomainPackConflictError(
                    f"domain pack is referenced by committed domain results: {references[:5]}"
                )
            family_references = self._family_detection_references(pack_id, version)
            if family_references:
                raise DomainPackConflictError(
                    "domain pack is referenced by committed family detections: "
                    f"{family_references[:5]}"
                )
            directory = self._pack_dir(pack_id, version)
            if directory.is_symlink() or not directory.is_dir():
                raise DomainPackStoreCorruptError("installed domain pack path is unsafe")
            shutil.rmtree(directory)
            parent = directory.parent
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()

    def load(
        self,
        pack_id: str,
        version: str | None = None,
        *,
        enforce_compatibility: bool = True,
    ) -> LoadedDomainPack:
        if version is None:
            state = self._read_state()
            version = state["active"].get(pack_id)
            if version is None:
                raise FileNotFoundError(f"no active domain pack: {pack_id}")
        return self._read_installed(
            pack_id, version, enforce_compatibility=enforce_compatibility
        )

    def list_records(self) -> list[DomainPackRecord]:
        state = self._read_state()
        records: list[DomainPackRecord] = []
        for pack_dir in sorted(self.packs_dir.iterdir()):
            if not pack_dir.is_dir() or pack_dir.is_symlink() or pack_dir.name.startswith("."):
                continue
            for version_dir in sorted(pack_dir.iterdir()):
                if not version_dir.is_dir() or version_dir.is_symlink():
                    continue
                pack = self._read_installed(
                    pack_dir.name, version_dir.name, enforce_compatibility=False
                )
                records.append(
                    self._record(
                        pack,
                        active=state["active"].get(pack_dir.name) == version_dir.name,
                    )
                )
        return records

    def _domain_result_references(self, pack_id: str, version: str) -> list[str]:
        from document_intelligence.domain_runtime.store import DomainResultStore

        result_store = DomainResultStore(self.workspace)
        references: list[str] = []
        for result_id in result_store.list_ids():
            try:
                result = result_store.read(result_id)
            except Exception as exc:
                raise DomainPackStoreCorruptError(
                    "cannot evaluate domain pack references because a domain result is corrupt"
                ) from exc
            if result.pack_id == pack_id and result.pack_version == version:
                references.append(result_id)
        return sorted(references)

    def _family_detection_references(self, pack_id: str, version: str) -> list[str]:
        from document_intelligence.family.store import FamilyDetectionStore

        detection_store = FamilyDetectionStore(self.workspace)
        references: list[str] = []
        for detection_id in detection_store.list_ids():
            try:
                result = detection_store.read(detection_id)
            except Exception as exc:
                raise DomainPackStoreCorruptError(
                    "cannot evaluate domain pack references because a family detection is corrupt"
                ) from exc
            if any(
                candidate.pack_id == pack_id and candidate.pack_version == version
                for candidate in result.candidates
            ):
                references.append(detection_id)
        return sorted(references)

    def _record(self, pack: LoadedDomainPack, *, active: bool | None = None) -> DomainPackRecord:
        metadata = self._read_metadata(pack.root)
        if active is None:
            active = self._read_state()["active"].get(pack.manifest.id) == pack.manifest.version
        return DomainPackRecord(
            pack_id=pack.manifest.id,
            version=pack.manifest.version,
            content_digest=pack.content_digest,
            installed_at=float(metadata["installed_at"]),
            active=active,
            signature_verified=bool(metadata["signature_verified"]),
            capabilities=pack.manifest.capabilities,
            permissions=pack.manifest.permissions,
            has_family_profile=pack.family is not None,
            family_id=pack.family.family_id if pack.family else None,
        )

    def _read_installed(
        self, pack_id: str, version: str, *, enforce_compatibility: bool = True
    ) -> LoadedDomainPack:
        directory = self._pack_dir(pack_id, version)
        if not directory.is_dir() or directory.is_symlink():
            raise FileNotFoundError(f"domain pack not installed: {pack_id}@{version}")
        try:
            metadata = self._read_metadata(directory)
            pack = load_domain_pack(directory, signature_verified=False)
            signature_verified = self._verify_signature(pack.manifest)
            if bool(metadata["signature_verified"]) != signature_verified:
                raise ValueError("installed domain pack signature metadata mismatch")
            pack = pack.model_copy(update={"signature_verified": signature_verified})
            if pack.manifest.id != pack_id or pack.manifest.version != version:
                raise ValueError("installed domain pack identity differs from its path")
            if metadata["pack_id"] != pack_id or metadata["pack_version"] != version:
                raise ValueError("installed domain pack metadata identity mismatch")
            if metadata["content_digest"] != pack.content_digest:
                raise ValueError("installed domain pack metadata digest mismatch")
            if enforce_compatibility:
                self._assert_compatible(pack.manifest)
            return pack
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            raise DomainPackStoreCorruptError(
                f"installed domain pack failed integrity verification: {exc}"
            ) from exc

    def _read_metadata(self, directory: Path) -> dict[str, Any]:
        path = directory / ".installed.json"
        if path.is_symlink() or not path.is_file():
            raise DomainPackStoreCorruptError("installed domain pack metadata is missing")
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if metadata.get("version") != 1:
            raise DomainPackStoreCorruptError("unsupported installed domain pack metadata")
        return metadata

    def _assert_compatible(self, manifest: DomainPackManifest) -> None:
        if not manifest.supports(
            core_schema_version=SCHEMA_VERSION, engine_version=self.engine_version
        ):
            raise DomainPackCompatibilityError(
                f"domain pack {manifest.id}@{manifest.version} is incompatible with "
                f"core_schema={SCHEMA_VERSION}, engine={self.engine_version}"
            )

    def _verify_signature(self, manifest: DomainPackManifest) -> bool:
        if manifest.signature is None:
            if self.require_signatures:
                raise DomainPackSignatureError("unsigned domain packs are not allowed")
            return False
        key_text = self.trusted_public_keys.get(manifest.signing_key_id or "")
        if key_text is None:
            raise DomainPackSignatureError("domain pack signing key is not trusted")
        try:
            public_bytes = base64.b64decode(key_text, validate=True)
            signature = base64.b64decode(manifest.signature, validate=True)
            Ed25519PublicKey.from_public_bytes(public_bytes).verify(
                signature, manifest.canonical_signing_payload()
            )
        except (ValueError, InvalidSignature) as exc:
            raise DomainPackSignatureError("domain pack signature verification failed") from exc
        return True

    def _extract_archive(self, archive: bytes, temp_root: Path) -> Path:
        archive_path = temp_root / "upload.zip"
        archive_path.write_bytes(archive)
        extract_root = temp_root / "extracted"
        extract_root.mkdir()
        try:
            with zipfile.ZipFile(archive_path) as source:
                infos = source.infolist()
                if not infos or len(infos) > self.max_archive_files:
                    raise DomainPackArchiveError("domain pack archive file count is invalid")
                total = 0
                roots: set[str] = set()
                for info in infos:
                    if info.flag_bits & 0x1:
                        raise DomainPackArchiveError(
                            "encrypted domain pack archives are not allowed"
                        )
                    path = PurePosixPath(info.filename)
                    if path.is_absolute() or ".." in path.parts or not path.parts:
                        raise DomainPackArchiveError("domain pack archive contains unsafe paths")
                    mode = (info.external_attr >> 16) & 0xFFFF
                    file_type = stat.S_IFMT(mode)
                    if stat.S_ISLNK(mode) or file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                        raise DomainPackArchiveError("domain pack archive contains special files")
                    if info.file_size < 0 or info.compress_size < 0:
                        raise DomainPackArchiveError("domain pack archive contains invalid sizes")
                    total += info.file_size
                    if total > self.max_archive_bytes:
                        raise DomainPackArchiveError(
                            "domain pack archive expands beyond size limit"
                        )
                    if info.file_size and info.compress_size == 0:
                        raise DomainPackArchiveError(
                            "domain pack archive has invalid compression metadata"
                        )
                    if (
                        info.compress_size
                        and info.file_size / info.compress_size > self.max_compression_ratio
                    ):
                        raise DomainPackArchiveError(
                            "domain pack archive compression ratio is unsafe"
                        )
                    roots.add(path.parts[0])
                    destination = extract_root.joinpath(*path.parts)
                    resolved = destination.resolve()
                    extract_resolved = extract_root.resolve()
                    if (
                        extract_resolved not in resolved.parents
                        and resolved != extract_resolved
                    ):
                        raise DomainPackArchiveError(
                            "domain pack archive path escapes extraction root"
                        )
                    if info.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(info) as source_handle, destination.open("wb") as target:
                        shutil.copyfileobj(source_handle, target, length=1024 * 1024)
                direct_manifest = extract_root / "manifest.yaml"
                if direct_manifest.is_file():
                    return extract_root
                candidate_roots = [
                    extract_root / name
                    for name in roots
                    if (extract_root / name / "manifest.yaml").is_file()
                ]
                if len(candidate_roots) != 1:
                    raise DomainPackArchiveError(
                        "archive must contain manifest.yaml at root or one top-level directory"
                    )
                return candidate_roots[0]
        except zipfile.BadZipFile as exc:
            raise DomainPackArchiveError("domain pack archive is not a valid ZIP") from exc

    @staticmethod
    def _load_manifest(root: Path) -> DomainPackManifest:
        path = root / "manifest.yaml"
        try:
            return DomainPackManifest.model_validate(
                __import__("yaml").safe_load(path.read_text(encoding="utf-8"))
            )
        except Exception as exc:
            raise DomainPackArchiveError(f"domain pack manifest is invalid: {exc}") from exc

    def _pack_dir(self, pack_id: str, version: str) -> Path:
        validate_safe_id(pack_id, field_name="pack_id")
        safe_version = version.replace("+", "_")
        validate_safe_id(safe_version, field_name="pack_version")
        root = self.packs_dir.resolve()
        path = (self.packs_dir / pack_id / safe_version).resolve()
        if root not in path.parents:
            raise ValueError("domain pack path escapes registry namespace")
        return path

    def _read_state(self) -> dict[str, Any]:
        try:
            if self.state_path.is_symlink():
                raise ValueError("registry state is unsafe")
            if not self.state_path.exists():
                return {"version": 1, "active": {}}
            if not self.state_path.is_file():
                raise ValueError("registry state is unsafe")
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if state.get("version") != 1 or not isinstance(state.get("active"), dict):
                raise ValueError("unsupported domain pack registry state")
            return state
        except (ValueError, json.JSONDecodeError) as exc:
            raise DomainPackStoreCorruptError(
                f"domain pack registry state is corrupt: {exc}"
            ) from exc

    class _Lock:
        def __init__(self, path: Path) -> None:
            self.path = path
            self.fd: int | None = None

        def __enter__(self) -> None:
            deadline = time.monotonic() + 10.0
            while True:
                try:
                    self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    os.write(self.fd, f"{os.getpid()}\n".encode())
                    return None
                except FileExistsError:
                    try:
                        age = time.time() - self.path.stat().st_mtime
                        if age > 300 and not self._owner_alive():
                            self.path.unlink(missing_ok=True)
                            continue
                    except FileNotFoundError:
                        continue
                    if time.monotonic() >= deadline:
                        raise TimeoutError("timed out acquiring domain pack registry lock")
                    time.sleep(0.05)

        def _owner_alive(self) -> bool:
            try:
                raw = self.path.read_text(encoding="utf-8").strip()
                pid = int(raw)
                if pid <= 0:
                    return False
                os.kill(pid, 0)
                return True
            except ProcessLookupError:
                return False
            except (PermissionError, ValueError, OSError):
                return True

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            if self.fd is not None:
                os.close(self.fd)
            self.path.unlink(missing_ok=True)

    def _lock(self) -> _Lock:
        return self._Lock(self.lock_path)

    @staticmethod
    def _atomic_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode()
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise
