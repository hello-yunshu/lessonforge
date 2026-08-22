"""Fail-closed download, probe, activation and rollback for official Runtime bytes."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Any, Literal

from document_intelligence.rill.adoption import (
    ReleaseArtifact,
    RillAdoptionLock,
    RillDistributionError,
    load_adoption_lock,
    select_runtime,
    verify_locked_release_index,
    verify_artifact_bytes,
    verify_artifact_file,
)


class RillRuntimeManager:
    """Own only distribution state; the Runtime binary remains upstream-owned."""

    _process_lock = threading.RLock()

    def __init__(self, app_data: Path, *, max_artifact_bytes: int = 128 * 1024 * 1024) -> None:
        self.app_data = app_data
        self.max_artifact_bytes = max_artifact_bytes
        self.root = app_data / "rill"
        self.downloads = self.root / "downloads"
        self.runtimes = self.root / "runtimes"
        self.active_metadata = self.root / "active.json"
        self.previous_metadata = self.root / "previous.json"
        self.lock_path = self.root / "install.lock"

    def stage_bytes(self, data: bytes, artifact: ReleaseArtifact) -> Path:
        if len(data) > self.max_artifact_bytes:
            raise RillDistributionError(
                "RILL_ARTIFACT_TOO_LARGE", "Rill artifact exceeds the configured limit"
            )
        verify_artifact_bytes(data, artifact)
        self.downloads.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=f"{artifact.version}-", suffix=".staged", dir=self.downloads, delete=False
        ) as handle:
            staging = Path(handle.name)
            handle.write(data)
        try:
            staging.chmod(0o700)
        except OSError as exc:
            staging.unlink(missing_ok=True)
            raise RillDistributionError(
                "RILL_PERMISSION_DENIED", "cannot make staged Rill artifact executable"
            ) from exc
        return staging

    def download_and_stage(
        self,
        artifact: ReleaseArtifact,
        *,
        timeout_seconds: float = 30.0,
        opener: Any = urllib.request.urlopen,
    ) -> Path:
        self.downloads.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        total = 0
        digest = hashlib.sha256()
        completed = False
        try:
            with (
                opener(artifact.url, timeout=timeout_seconds) as response,
                tempfile.NamedTemporaryFile(
                    prefix=f"{artifact.version}-",
                    suffix=".download",
                    dir=self.downloads,
                    delete=False,
                ) as handle,
            ):
                temporary = Path(handle.name)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > min(self.max_artifact_bytes, artifact.size):
                        raise RillDistributionError(
                            "RILL_ARTIFACT_TOO_LARGE", "Rill download exceeded its indexed size"
                        )
                    digest.update(chunk)
                    handle.write(chunk)
            if total != artifact.size:
                raise RillDistributionError(
                    "RILL_ARTIFACT_SIZE_MISMATCH", "Rill download ended at the wrong size"
                )
            if digest.hexdigest() != artifact.sha256:
                raise RillDistributionError(
                    "RILL_ARTIFACT_SHA256_MISMATCH", "Rill download digest differs from the index"
                )
            assert temporary is not None
            temporary.chmod(0o700)
            completed = True
            return temporary
        except RillDistributionError:
            raise
        except (OSError, ValueError) as exc:
            raise RillDistributionError(
                "RILL_DOWNLOAD_FAILED", "Rill artifact download failed"
            ) from exc
        finally:
            if temporary is not None and temporary.exists() and not completed:
                temporary.unlink(missing_ok=True)

    def activate(
        self,
        staging: Path,
        artifact: ReleaseArtifact,
        *,
        lock: RillAdoptionLock,
        probe_timeout_seconds: float = 5.0,
    ) -> Path:
        if staging.is_symlink() or not staging.is_file():
            raise RillDistributionError(
                "RILL_STAGING_INVALID", "Rill staging path is not a regular file"
            )
        if (
            artifact.version != lock.supported
            or artifact.runtime_api_version != lock.stable_runtime_api
        ):
            raise RillDistributionError(
                "RILL_ARTIFACT_IDENTITY_MISMATCH",
                "Rill staging artifact is not the locked stable runtime",
            )
        verify_artifact_file(staging, artifact)
        destination = self.runtimes / lock.supported / self._target_name(artifact)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._process_lock, self._locked_install():
            try:
                staging.chmod(0o700)
            except OSError as exc:
                raise RillDistributionError(
                    "RILL_PERMISSION_DENIED", "cannot prepare Rill runtime permissions"
                ) from exc
            self._probe(staging, timeout_seconds=probe_timeout_seconds)
            os.replace(staging, destination)
            old_active = self._read_metadata(self.active_metadata)
            if old_active is not None:
                self._atomic_json(self.previous_metadata, old_active)
            self._atomic_json(
                self.active_metadata,
                {
                    "supported": lock.supported,
                    "tag": lock.tag,
                    "commit": lock.commit,
                    "targetOs": artifact.target_os,
                    "targetArch": artifact.target_arch,
                    "targetLibc": artifact.target_libc,
                    "version": artifact.version,
                    "path": str(destination),
                    "sha256": artifact.sha256,
                },
            )
        return destination

    def rollback(self) -> Path:
        with self._process_lock, self._locked_install():
            previous = self._read_metadata(self.previous_metadata)
            if previous is None:
                raise RillDistributionError(
                    "RILL_ROLLBACK_UNAVAILABLE", "no previous-good Rill runtime exists"
                )
            previous_path = Path(str(previous.get("path", "")))
            if previous_path.is_symlink() or not previous_path.is_file():
                raise RillDistributionError(
                    "RILL_ROLLBACK_INVALID", "previous Rill runtime is not available"
                )
            self._verify_recorded_digest(previous_path, previous)
            current = self._read_metadata(self.active_metadata)
            self._atomic_json(self.active_metadata, previous)
            if current is not None:
                self._atomic_json(self.previous_metadata, current)
            return previous_path

    def active(self) -> dict[str, Any] | None:
        return self._read_metadata(self.active_metadata)

    def _probe(self, executable: Path, *, timeout_seconds: float) -> None:
        try:
            completed = subprocess.run(
                [str(executable), "--version"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                check=False,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RillDistributionError(
                "RILL_EXECUTABLE_PROBE_FAILED", "Rill runtime executable probe failed"
            ) from exc
        if completed.returncode != 0:
            raise RillDistributionError(
                "RILL_EXECUTABLE_PROBE_FAILED", "Rill runtime --version probe failed"
            )

    @staticmethod
    def _verify_recorded_digest(path: Path, metadata: dict[str, Any]) -> None:
        expected = str(metadata.get("sha256", ""))
        if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
            raise RillDistributionError(
                "RILL_ROLLBACK_INVALID", "previous Rill runtime metadata has no valid digest"
            )
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise RillDistributionError(
                "RILL_ROLLBACK_INVALID", "previous Rill runtime cannot be read"
            ) from exc
        if digest.hexdigest() != expected:
            raise RillDistributionError(
                "RILL_ROLLBACK_INVALID", "previous Rill runtime digest differs from metadata"
            )

    @staticmethod
    def _target_name(artifact: ReleaseArtifact) -> str:
        suffix = ".exe" if artifact.target_os == "windows" else ""
        libc = f"-{artifact.target_libc}" if artifact.target_libc else ""
        # Include the immutable digest so a same-version reactivation cannot
        # overwrite the previous-good bytes that rollback must preserve.
        return f"{artifact.target_os}-{artifact.target_arch}{libc}-{artifact.sha256[:12]}{suffix}"

    def _read_metadata(self, path: Path) -> dict[str, Any] | None:
        try:
            if not path.is_file() or path.is_symlink():
                return None
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except (OSError, ValueError):
            return None

    @staticmethod
    def _atomic_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
        os.replace(temporary, path)

    class _Lock:
        def __init__(self, path: Path) -> None:
            self.path = path
            self.handle: Any = None

        def __enter__(self) -> RillRuntimeManager._Lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = self.path.open("a+b")
            try:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
            except ImportError:
                try:
                    import msvcrt

                    self.handle.seek(0)
                    self.handle.write(b"0")
                    self.handle.flush()
                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
                except (ImportError, OSError) as exc:
                    self.handle.close()
                    self.handle = None
                    raise RillDistributionError(
                        "RILL_INSTALL_LOCK_UNSUPPORTED",
                        "cross-process Rill install locking is unavailable on this platform",
                    ) from exc
            return self

        def __exit__(self, *_: object) -> None:
            if self.handle is None:
                return
            try:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            except ImportError:
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            self.handle.close()

    def _locked_install(self) -> RillRuntimeManager._Lock:
        return self._Lock(self.lock_path)


class RillAdoptionManager(RillRuntimeManager):
    """Install and qualify one complete Runtime/model/handler bundle.

    The manager owns only consumer distribution state.  Runtime bytes remain
    official upstream release assets; the model and handler are LessonForge
    consumer artifacts signed with a separate trust key.  A bundle is active
    only after package verification and a real Stable v2 handshake, health and
    invoke probe have all succeeded.
    """

    def __init__(self, app_data: Path, *, max_artifact_bytes: int = 128 * 1024 * 1024) -> None:
        super().__init__(app_data, max_artifact_bytes=max_artifact_bytes)
        self.bundles = self.root / "bundles"
        self.active_bundle_metadata = self.root / "active-bundle.json"
        self.previous_bundle_metadata = self.root / "previous-bundle.json"

    def active_bundle(self) -> dict[str, Any] | None:
        value = self._read_metadata(self.active_bundle_metadata)
        if value is None:
            return None
        if value.get("qualification") != "VERIFIED":
            return value
        required = ("runtime", "model", "handler", "command", "capabilities")
        if any(key not in value for key in required):
            return {**value, "qualification": "INVALID_BUNDLE"}
        for item_name in ("runtime", "model", "handler"):
            item = value[item_name]
            if not isinstance(item, dict):
                return {**value, "qualification": "INVALID_BUNDLE"}
            path = Path(str(item.get("path", "")))
            if path.is_symlink() or not path.is_file():
                return {**value, "qualification": "INVALID_BUNDLE"}
            try:
                if hashlib.sha256(path.read_bytes()).hexdigest() != item.get("sha256"):
                    return {**value, "qualification": "INVALID_BUNDLE"}
            except OSError:
                return {**value, "qualification": "INVALID_BUNDLE"}
        return value

    def status(self, lock: RillAdoptionLock | None = None) -> dict[str, Any]:
        adoption = lock or load_adoption_lock()
        bundle = self.active_bundle()
        if bundle is None:
            qualification = "NOT_INSTALLED"
        elif bundle.get("qualification") == "VERIFIED":
            qualification = "VERIFIED"
        else:
            qualification = str(bundle.get("qualification", "INVALID_BUNDLE"))
        result: dict[str, Any] = {
            "upstreamLatestStable": adoption.upstream_latest_stable,
            "supported": adoption.supported,
            "tested": adoption.tested,
            "installed": adoption.supported if qualification == "VERIFIED" else None,
            "runtimeApi": adoption.stable_runtime_api,
            "protocol": adoption.production_protocol,
            "qualification": qualification,
            "hostOwnedFeedback": True,
            "runtimeReset": False,
        }
        if bundle is not None:
            result.update(
                {
                    "model": {
                        "id": bundle.get("model", {}).get("id"),
                        "version": bundle.get("model", {}).get("version"),
                        "sha256": bundle.get("model", {}).get("sha256"),
                    },
                    "handler": {
                        "id": bundle.get("handler", {}).get("id"),
                        "version": bundle.get("handler", {}).get("version"),
                        "api": bundle.get("handler", {}).get("api"),
                        "sha256": bundle.get("handler", {}).get("sha256"),
                    },
                    "capabilities": bundle.get("capabilities", []),
                    "runtimeSha256": bundle.get("runtime", {}).get("sha256"),
                }
            )
        return result

    def install_bundle(
        self,
        raw_index: bytes,
        *,
        model_path: Path,
        handler_path: Path,
        model_id: str,
        model_version: str,
        handler_id: str,
        handler_version: str,
        model_key_id: str,
        model_public_key: str,
        handler_key_id: str,
        handler_public_key: str,
        rill_pack_command: tuple[str, ...] = ("rill-pack",),
        feature_schema_hash: str = "0" * 64,
        target: tuple[str, str, str | None] | None = None,
        runtime_path: Path | None = None,
        timeout_seconds: float = 30.0,
        opener: Any = urllib.request.urlopen,
    ) -> dict[str, Any]:
        lock = load_adoption_lock()
        index = verify_locked_release_index(raw_index, lock=lock)
        runtime_artifact = select_runtime(index, target=target, lock=lock)
        if model_version != lock.supported or handler_version != lock.supported:
            raise RillDistributionError(
                "RILL_CONSUMER_VERSION_MISMATCH",
                "LessonForge consumer model and handler must be qualified for RillML 1.2.0",
            )
        model_artifact = self._local_artifact(
            "model", model_id, model_version, model_path, runtime_api=lock.stable_runtime_api
        )
        handler_artifact = self._local_artifact(
            "handler",
            handler_id,
            handler_version,
            handler_path,
            runtime_api=lock.stable_runtime_api,
            handler_api=1,
        )
        for path, artifact in (
            (model_path, model_artifact),
            (handler_path, handler_artifact),
        ):
            verify_artifact_file(path, artifact)
        model_inspection = self._verify_package(
            rill_pack_command,
            "model",
            model_path,
            model_key_id,
            model_public_key,
        )
        handler_inspection = self._verify_package(
            rill_pack_command,
            "handler",
            handler_path,
            handler_key_id,
            handler_public_key,
        )
        if (
            model_inspection.get("id") != model_id
            or model_inspection.get("version") != model_version
            or model_inspection.get("publisherKeyId") != model_key_id
            or model_inspection.get("runtimeApiVersion") != lock.stable_runtime_api
            or model_inspection.get("capabilities") != ["org.lessonforge.shadow.evaluate"]
        ):
            raise RillDistributionError(
                "RILL_MODEL_IDENTITY_MISMATCH",
                "verified model metadata differs from the adoption bundle",
            )
        if (
            handler_inspection.get("id") != handler_id
            or handler_inspection.get("version") != handler_version
            or handler_inspection.get("publisherKeyId") != handler_key_id
            or handler_inspection.get("handlerApiVersion") != 1
            or handler_inspection.get("capabilities") != ["org.lessonforge.shadow.evaluate"]
        ):
            raise RillDistributionError(
                "RILL_HANDLER_IDENTITY_MISMATCH",
                "verified handler metadata differs from the adoption bundle",
            )
        if runtime_path is None:
            runtime_staging = self.download_and_stage(
                runtime_artifact, timeout_seconds=timeout_seconds, opener=opener
            )
            runtime_is_temporary = True
        else:
            verify_artifact_file(runtime_path, runtime_artifact)
            runtime_staging = runtime_path
            runtime_is_temporary = False
        bundle_id = (
            f"{lock.supported}-{runtime_artifact.sha256[:12]}-"
            f"{handler_artifact.sha256[:12]}"
        )
        bundle_dir = self.bundles / bundle_id
        bundle_dir.mkdir(parents=True, exist_ok=True)
        runtime_destination = bundle_dir / self._target_name(runtime_artifact)
        model_destination = bundle_dir / f"{model_id}-{model_version}.rillpack"
        handler_destination = bundle_dir / f"{handler_id}-{handler_version}.rillhandler"
        try:
            if runtime_is_temporary:
                os.replace(runtime_staging, runtime_destination)
            else:
                shutil.copyfile(runtime_staging, runtime_destination)
            shutil.copyfile(model_path, model_destination)
            shutil.copyfile(handler_path, handler_destination)
            runtime_destination.chmod(0o700)
        except OSError as exc:
            if runtime_is_temporary:
                runtime_staging.unlink(missing_ok=True)
            raise RillDistributionError(
                "RILL_BUNDLE_STAGE_FAILED", "Rill adoption bundle staging failed"
            ) from exc
        command = (
            str(runtime_destination),
            "serve",
            "--pack",
            str(model_destination),
            "--handler",
            str(handler_destination),
            "--model-trust-key",
            f"{model_key_id}={model_public_key.lower()}",
            "--handler-trust-key",
            f"{handler_key_id}={handler_public_key.lower()}",
        )
        from document_intelligence.rill.stable_client import StableV2RillClient

        client = StableV2RillClient(
            command,
            feature_schema_hash=feature_schema_hash,
            feedback_capability=None,
            expected_runtime_sha256=runtime_artifact.sha256,
            expected_runtime_version=lock.supported,
            expected_model_pack_id=model_id,
            expected_model_pack_version=model_version,
            expected_handler_id=handler_id,
            expected_handler_version=handler_version,
            expected_effective_capabilities=["org.lessonforge.shadow.evaluate"],
            startup_timeout_seconds=10,
            request_timeout_seconds=10,
        )
        try:
            output = client.invoke(
                "org.lessonforge.shadow.evaluate",
                {
                    "operation": "qualification",
                    "allowedActions": ["HUMAN_REVIEW"],
                    "features": {},
                },
            )
            if not isinstance(output, dict) or not isinstance(output.get("suggestion"), dict):
                raise RillDistributionError(
                    "RILL_BUNDLE_INVOKE_INVALID", "Rill handler qualification output is invalid"
                )
        finally:
            client.close()
        metadata = {
            "schemaVersion": 1,
            "qualification": "VERIFIED",
            "rillRelease": lock.supported,
            "runtimeApi": lock.stable_runtime_api,
            "handlerApi": 1,
            "capabilities": ["org.lessonforge.shadow.evaluate"],
            "hostOwnedFeedback": True,
            "runtimeReset": False,
            "runtime": {
                "version": runtime_artifact.version,
                "path": str(runtime_destination),
                "sha256": runtime_artifact.sha256,
                "targetOs": runtime_artifact.target_os,
                "targetArch": runtime_artifact.target_arch,
                "targetLibc": runtime_artifact.target_libc,
            },
            "model": {
                "id": model_id,
                "version": model_version,
                "path": str(model_destination),
                "sha256": model_artifact.sha256,
                "publisherKeyId": model_key_id,
            },
            "handler": {
                "id": handler_id,
                "version": handler_version,
                "api": 1,
                "path": str(handler_destination),
                "sha256": handler_artifact.sha256,
                "publisherKeyId": handler_key_id,
            },
            "command": list(command),
        }
        with self._process_lock, self._locked_install():
            old_active = self._read_metadata(self.active_bundle_metadata)
            if old_active is not None:
                self._atomic_json(self.previous_bundle_metadata, old_active)
            self._atomic_json(self.active_bundle_metadata, metadata)
        return metadata

    def rollback_bundle(self) -> dict[str, Any]:
        with self._process_lock, self._locked_install():
            previous = self._read_metadata(self.previous_bundle_metadata)
            if previous is None:
                raise RillDistributionError(
                    "RILL_ROLLBACK_UNAVAILABLE", "no previous-good Rill adoption bundle exists"
                )
            candidate = self._validate_bundle_files(previous)
            current = self._read_metadata(self.active_bundle_metadata)
            self._atomic_json(self.active_bundle_metadata, candidate)
            if current is not None:
                self._atomic_json(self.previous_bundle_metadata, current)
            return candidate

    @staticmethod
    def _local_artifact(
        kind: Literal["model", "handler"],
        artifact_id: str,
        version: str,
        path: Path,
        *,
        runtime_api: int,
        handler_api: int | None = None,
    ) -> ReleaseArtifact:
        return ReleaseArtifact(
            kind=kind,
            id=artifact_id,
            version=version,
            runtimeApiVersion=runtime_api,
            handlerApiVersion=handler_api,
            minRuntimeVersion="1.2.0" if kind == "handler" else None,
            url=f"https://local.invalid/{artifact_id}/{version}",
            sha256=RillAdoptionManager._sha256(path),
            size=path.stat().st_size,
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _verify_package(
        command: tuple[str, ...],
        kind: str,
        path: Path,
        key_id: str,
        public_key: str,
    ) -> dict[str, Any]:
        operation = "verify" if kind == "model" else "inspect-handler"
        flag = "--pack" if kind == "model" else "--handler"
        try:
            completed = subprocess.run(
                [
                    *command,
                    operation,
                    flag,
                    str(path),
                    "--key-id",
                    key_id,
                    "--public-key-hex",
                    public_key,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RillDistributionError(
                "RILL_PACKAGE_VERIFY_FAILED", f"signed Rill {kind} package verification failed"
            ) from exc
        if completed.returncode != 0:
            raise RillDistributionError(
                "RILL_PACKAGE_SIGNATURE_INVALID", f"signed Rill {kind} package verification failed"
            )
        try:
            value = json.loads(completed.stdout)
        except ValueError as exc:
            raise RillDistributionError(
                "RILL_PACKAGE_METADATA_INVALID", f"signed Rill {kind} package metadata is invalid"
            ) from exc
        if not isinstance(value, dict) or value.get("signatureVerified") is not True:
            raise RillDistributionError(
                "RILL_PACKAGE_SIGNATURE_INVALID", f"signed Rill {kind} package is not verified"
            )
        return value

    def _validate_bundle_files(self, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("qualification") != "VERIFIED":
            raise RillDistributionError("RILL_ROLLBACK_INVALID", "previous bundle was not verified")
        for item_name in ("runtime", "model", "handler"):
            item = value.get(item_name)
            if not isinstance(item, dict):
                raise RillDistributionError(
                    "RILL_ROLLBACK_INVALID", "previous bundle metadata is invalid"
                )
            path = Path(str(item.get("path", "")))
            if path.is_symlink() or not path.is_file() or self._sha256(path) != item.get("sha256"):
                raise RillDistributionError(
                    "RILL_ROLLBACK_INVALID", "previous bundle bytes are invalid"
                )
        return value
