from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterator
from typing import TypeVar

from pydantic import BaseModel

from document_intelligence.exceptions import RillStoreCorruptError
from document_intelligence.rill.assist_models import (
    AssistActivationRecord,
    AssistEvidenceAttestation,
    AssistExecutionRecord,
    AssistQualificationReport,
    AssistQueueItem,
    AssistRevocationRecord,
    AssistParserSuspensionRecord,
    AssistParserResumeRecord,
)
from document_intelligence.schema import validate_safe_id

T = TypeVar("T", bound=BaseModel)


class RillAssistStore:
    def __init__(self, workspace: Path) -> None:
        self.root = workspace / "rill-assist"
        if self.root.is_symlink():
            raise ValueError("Rill Assist root cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        self.attestations_dir = self._namespace("attestations")
        self.qualifications_dir = self._namespace("qualifications")
        self.activations_dir = self._namespace("activations")
        self.revocations_dir = self._namespace("revocations")
        self.executions_dir = self._namespace("executions")
        self.queue_dir = self._namespace("queue")
        self.suspensions_dir = self._namespace("parser-suspensions")
        self.resumes_dir = self._namespace("parser-resumes")
        self.locks_dir = self._namespace("locks")

    def commit_attestation(self, value: AssistEvidenceAttestation) -> AssistEvidenceAttestation:
        return self._commit(self.attestations_dir, value.attestation_id, "attestation.json", value)

    def list_attestations(self) -> list[AssistEvidenceAttestation]:
        return self._list(self.attestations_dir, "attestation.json", AssistEvidenceAttestation)

    def commit_qualification(self, value: AssistQualificationReport) -> AssistQualificationReport:
        return self._commit(self.qualifications_dir, value.report_id, "qualification.json", value)

    def read_qualification(self, report_id: str) -> AssistQualificationReport:
        return self._read(
            self.qualifications_dir,
            report_id,
            "qualification.json",
            AssistQualificationReport,
        )

    def list_qualifications(self) -> list[AssistQualificationReport]:
        return self._list(self.qualifications_dir, "qualification.json", AssistQualificationReport)

    def commit_activation(self, value: AssistActivationRecord) -> AssistActivationRecord:
        return self._commit(self.activations_dir, value.activation_id, "activation.json", value)

    def read_activation(self, activation_id: str) -> AssistActivationRecord:
        return self._read(
            self.activations_dir,
            activation_id,
            "activation.json",
            AssistActivationRecord,
        )

    def list_activations(self) -> list[AssistActivationRecord]:
        return self._list(self.activations_dir, "activation.json", AssistActivationRecord)

    def commit_revocation(self, value: AssistRevocationRecord) -> AssistRevocationRecord:
        return self._commit(self.revocations_dir, value.revocation_id, "revocation.json", value)

    def list_revocations(self) -> list[AssistRevocationRecord]:
        return self._list(self.revocations_dir, "revocation.json", AssistRevocationRecord)

    def revocation_for_activation(self, activation_id: str) -> AssistRevocationRecord | None:
        matches = [item for item in self.list_revocations() if item.activation_id == activation_id]
        if len(matches) > 1:
            raise RillStoreCorruptError("multiple revocations exist for one Assist activation")
        return matches[0] if matches else None

    def commit_execution(self, value: AssistExecutionRecord) -> AssistExecutionRecord:
        return self._commit(self.executions_dir, value.execution_id, "execution.json", value)

    def read_execution(self, execution_id: str) -> AssistExecutionRecord:
        return self._read(
            self.executions_dir,
            execution_id,
            "execution.json",
            AssistExecutionRecord,
        )

    def list_executions(self) -> list[AssistExecutionRecord]:
        return self._list(self.executions_dir, "execution.json", AssistExecutionRecord)

    def commit_queue_item(self, value: AssistQueueItem) -> AssistQueueItem:
        return self._commit(self.queue_dir, value.queue_item_id, "queue-item.json", value)

    def list_queue_items(self) -> list[AssistQueueItem]:
        return self._list(self.queue_dir, "queue-item.json", AssistQueueItem)

    def commit_parser_suspension(
        self, value: AssistParserSuspensionRecord
    ) -> AssistParserSuspensionRecord:
        return self._commit(
            self.suspensions_dir, value.suspension_id, "suspension.json", value
        )

    def read_parser_suspension(self, suspension_id: str) -> AssistParserSuspensionRecord:
        return self._read(
            self.suspensions_dir, suspension_id, "suspension.json", AssistParserSuspensionRecord
        )

    def list_parser_suspensions(self) -> list[AssistParserSuspensionRecord]:
        return self._list(
            self.suspensions_dir, "suspension.json", AssistParserSuspensionRecord
        )

    def commit_parser_resume(
        self, value: AssistParserResumeRecord
    ) -> AssistParserResumeRecord:
        return self._commit(self.resumes_dir, value.resume_id, "resume.json", value)

    def list_parser_resumes(self) -> list[AssistParserResumeRecord]:
        return self._list(self.resumes_dir, "resume.json", AssistParserResumeRecord)

    def resume_for_suspension(self, suspension_id: str) -> AssistParserResumeRecord | None:
        matches = [
            item for item in self.list_parser_resumes() if item.suspension_id == suspension_id
        ]
        if len(matches) > 1:
            raise RillStoreCorruptError(
                "multiple resume records exist for one parser suspension"
            )
        return matches[0] if matches else None

    def active_parser_suspensions(
        self, parser_id: str | None = None, *, now: datetime | None = None
    ) -> list[AssistParserSuspensionRecord]:
        point = now or datetime.now(timezone.utc)
        if point.tzinfo is None:
            raise ValueError("suspension timestamp must be timezone-aware")
        resumes = {item.suspension_id for item in self.list_parser_resumes()}
        return [
            item
            for item in self.list_parser_suspensions()
            if item.suspension_id not in resumes
            and item.expires_at > point
            and (parser_id is None or item.parser_id == parser_id)
        ]

    def executions_since(self, activation_id: str, since: datetime) -> list[AssistExecutionRecord]:
        if since.tzinfo is None:
            raise ValueError("rate-limit timestamp must be timezone-aware")
        return [
            item
            for item in self.list_executions()
            if item.activation_id == activation_id and item.created_at >= since
        ]

    @contextmanager
    def activation_lock(
        self,
        activation_id: str,
        *,
        timeout_seconds: float = 30.0,
        stale_seconds: float = 600.0,
    ) -> Iterator[None]:
        safe_id = validate_safe_id(activation_id)
        self._validate_namespace(self.locks_dir)
        lock_path = self.locks_dir / f"{safe_id}.lock"
        deadline = time.monotonic() + timeout_seconds
        token = uuid.uuid4().hex
        fd: int | None = None
        while fd is None:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, f"pid={os.getpid()}\ntoken={token}\n".encode("ascii"))
                os.fsync(fd)
            except FileExistsError:
                try:
                    if self._lock_is_abandoned(lock_path, stale_seconds=stale_seconds):
                        lock_path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise RillStoreCorruptError("timed out acquiring Assist activation lock")
                time.sleep(0.05)
        try:
            yield
        finally:
            if fd is not None:
                os.close(fd)
            try:
                current = lock_path.read_text(encoding="ascii")
            except FileNotFoundError:
                return
            if f"token={token}\n" in current:
                lock_path.unlink(missing_ok=True)

    @staticmethod
    def _lock_is_abandoned(lock_path: Path, *, stale_seconds: float) -> bool:
        age = time.time() - lock_path.stat().st_mtime
        if age <= stale_seconds:
            return False
        try:
            payload = lock_path.read_text(encoding="ascii")
            pid_line = next(line for line in payload.splitlines() if line.startswith("pid="))
            pid = int(pid_line.removeprefix("pid="))
        except (OSError, StopIteration, ValueError):
            return True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False

    def _commit(self, namespace: Path, identifier: str, filename: str, value: T) -> T:
        safe_id = validate_safe_id(identifier)
        final_dir = self._safe_child(namespace, safe_id)
        if final_dir.exists():
            existing = self._read(namespace, safe_id, filename, type(value))
            if existing.semantic_digest() != value.semantic_digest():
                raise RillStoreCorruptError(
                    "Rill Assist identifier already contains different semantic content"
                )
            return existing
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{safe_id}.", dir=namespace))
        try:
            payload_path = temp_dir / filename
            payload = self._model_json(value)
            self._atomic_bytes(payload_path, payload)
            self._atomic_bytes(
                temp_dir / "manifest.json",
                self._canonical_json(
                    {
                        "version": 1,
                        "namespace": namespace.name,
                        "id": safe_id,
                        "filename": filename,
                        "payload_sha256": hashlib.sha256(payload).hexdigest(),
                        "semantic_digest": value.semantic_digest(),
                    }
                ),
            )
            try:
                os.rename(temp_dir, final_dir)
            except OSError as exc:
                if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY} and not final_dir.exists():
                    raise
                self._remove_tree(temp_dir)
        except Exception:
            self._remove_tree(temp_dir)
            raise
        committed = self._read(namespace, safe_id, filename, type(value))
        if committed.semantic_digest() != value.semantic_digest():
            raise RillStoreCorruptError("concurrent Assist commit produced different content")
        return committed

    def _read(self, namespace: Path, identifier: str, filename: str, model_type: type[T]) -> T:
        safe_id = validate_safe_id(identifier)
        directory = self._safe_child(namespace, safe_id)
        if not directory.is_dir():
            raise FileNotFoundError(safe_id)
        try:
            manifest_path = self._safe_file(directory, "manifest.json")
            payload_path = self._safe_file(directory, filename)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                manifest.get("version") != 1
                or manifest.get("namespace") != namespace.name
                or manifest.get("id") != safe_id
                or manifest.get("filename") != filename
            ):
                raise ValueError("Assist manifest identity mismatch")
            payload = payload_path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != manifest.get("payload_sha256"):
                raise ValueError("Assist payload digest mismatch")
            value = model_type.model_validate_json(payload)
            if value.semantic_digest() != manifest.get("semantic_digest"):
                raise ValueError("Assist semantic digest mismatch")
            return value
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise RillStoreCorruptError(
                f"stored Rill Assist record {safe_id} failed integrity verification"
            ) from exc

    def _list(self, namespace: Path, filename: str, model_type: type[T]) -> list[T]:
        self._validate_namespace(namespace)
        result: list[T] = []
        for directory in sorted(namespace.iterdir()):
            if directory.name.startswith("."):
                continue
            if directory.is_symlink() or not directory.is_dir():
                raise RillStoreCorruptError("Rill Assist namespace contains an invalid entry")
            result.append(self._read(namespace, directory.name, filename, model_type))
        return result

    def _namespace(self, name: str) -> Path:
        path = self.root / name
        if path.is_symlink():
            raise ValueError("Rill Assist namespace cannot be a symlink")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _validate_namespace(self, namespace: Path) -> None:
        if self.root.is_symlink() or namespace.is_symlink():
            raise RillStoreCorruptError("Rill Assist namespace cannot be a symbolic link")
        trusted_root = self.root.resolve()
        resolved = namespace.resolve()
        if trusted_root not in resolved.parents:
            raise RillStoreCorruptError("Rill Assist namespace escapes workspace")

    def _safe_child(self, parent: Path, name: str) -> Path:
        validate_safe_id(name)
        self._validate_namespace(parent)
        root = parent.resolve()
        candidate = (parent / name).resolve()
        if root not in candidate.parents:
            raise ValueError("Rill Assist identifier escapes namespace")
        return candidate

    @staticmethod
    def _safe_file(directory: Path, filename: str) -> Path:
        candidate = directory / filename
        if candidate.is_symlink():
            raise ValueError("Rill Assist artifacts cannot be symlinks")
        root = directory.resolve()
        resolved = candidate.resolve()
        if root not in resolved.parents or not resolved.is_file():
            raise FileNotFoundError(filename)
        return resolved

    @staticmethod
    def _model_json(value: BaseModel) -> bytes:
        return json.dumps(
            value.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def _canonical_json(value: dict[str, object]) -> bytes:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @staticmethod
    def _atomic_bytes(path: Path, payload: bytes) -> None:
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @staticmethod
    def _remove_tree(path: Path) -> None:
        if not path.exists():
            return
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_dir() and not child.is_symlink():
                child.rmdir()
            else:
                child.unlink(missing_ok=True)
        path.rmdir()
