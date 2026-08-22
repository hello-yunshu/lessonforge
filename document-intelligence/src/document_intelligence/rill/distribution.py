"""Fail-closed download, probe, activation and rollback for official Runtime bytes."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Any

from document_intelligence.rill.adoption import (
    ReleaseArtifact,
    RillAdoptionLock,
    RillDistributionError,
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
            self.handle = self.path.open("a+")
            try:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
            except ImportError:
                pass
            return self

        def __exit__(self, *_: object) -> None:
            if self.handle is None:
                return
            try:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            except ImportError:
                pass
            self.handle.close()

    def _locked_install(self) -> RillRuntimeManager._Lock:
        return self._Lock(self.lock_path)
