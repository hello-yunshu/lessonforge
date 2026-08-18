from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from document_intelligence.exceptions import DocumentIntelligenceError
from document_intelligence.mlops.models import (
    ActiveLearningBatch,
    AliasUpdateRecord,
    CandidateEvaluationReport,
    DatasetSnapshot,
    MLflowRunRecord,
    ModelAlias,
    ModelCandidate,
    ReleaseApproval,
    RollbackRecord,
    ShadowValidationReport,
)
from document_intelligence.schema import validate_safe_id

T = TypeVar("T", bound=BaseModel)


class MLOpsStoreError(DocumentIntelligenceError):
    code = "MLOPS_STORE_ERROR"
    severity = "P0"
    http_status = 500


class MLOpsStore:
    """Immutable Phase-7 records plus an audited alias pointer set."""

    def __init__(self, workspace: Path) -> None:
        self.root = workspace / "mlops"
        if self.root.is_symlink():
            raise ValueError("MLOps root cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        self.active_learning_dir = self._namespace("active-learning")
        self.snapshots_dir = self._namespace("dataset-snapshots")
        self.mlflow_dir = self._namespace("mlflow-runs")
        self.candidates_dir = self._namespace("candidates")
        self.evaluations_dir = self._namespace("evaluations")
        self.shadow_validations_dir = self._namespace("shadow-validations")
        self.approvals_dir = self._namespace("approvals")
        self.alias_updates_dir = self._namespace("alias-updates")
        self.rollbacks_dir = self._namespace("rollbacks")
        self.control_dir = self._namespace("control")
        self.locks_dir = self._namespace("locks")

    def commit_active_learning(self, value: ActiveLearningBatch) -> ActiveLearningBatch:
        return self._commit(
            self.active_learning_dir, value.batch_id, "batch.json", value
        )

    def read_active_learning(self, batch_id: str) -> ActiveLearningBatch:
        return self._read(
            self.active_learning_dir, batch_id, "batch.json", ActiveLearningBatch
        )

    def list_active_learning(self) -> list[ActiveLearningBatch]:
        return self._list(self.active_learning_dir, "batch.json", ActiveLearningBatch)

    def commit_snapshot(self, value: DatasetSnapshot) -> DatasetSnapshot:
        return self._commit(self.snapshots_dir, value.snapshot_id, "snapshot.json", value)

    def read_snapshot(self, snapshot_id: str) -> DatasetSnapshot:
        return self._read(self.snapshots_dir, snapshot_id, "snapshot.json", DatasetSnapshot)

    def list_snapshots(self) -> list[DatasetSnapshot]:
        return self._list(self.snapshots_dir, "snapshot.json", DatasetSnapshot)

    def commit_mlflow_run(self, value: MLflowRunRecord) -> MLflowRunRecord:
        return self._commit(self.mlflow_dir, value.record_id, "run.json", value)

    def read_mlflow_run(self, record_id: str) -> MLflowRunRecord:
        return self._read(self.mlflow_dir, record_id, "run.json", MLflowRunRecord)

    def list_mlflow_runs(self) -> list[MLflowRunRecord]:
        return self._list(self.mlflow_dir, "run.json", MLflowRunRecord)

    def commit_candidate(self, value: ModelCandidate) -> ModelCandidate:
        return self._commit(self.candidates_dir, value.candidate_id, "candidate.json", value)

    def read_candidate(self, candidate_id: str) -> ModelCandidate:
        return self._read(self.candidates_dir, candidate_id, "candidate.json", ModelCandidate)

    def list_candidates(self) -> list[ModelCandidate]:
        return self._list(self.candidates_dir, "candidate.json", ModelCandidate)

    def commit_evaluation(
        self, value: CandidateEvaluationReport
    ) -> CandidateEvaluationReport:
        return self._commit(
            self.evaluations_dir, value.report_id, "evaluation.json", value
        )

    def read_evaluation(self, report_id: str) -> CandidateEvaluationReport:
        return self._read(
            self.evaluations_dir,
            report_id,
            "evaluation.json",
            CandidateEvaluationReport,
        )

    def list_evaluations(self) -> list[CandidateEvaluationReport]:
        return self._list(
            self.evaluations_dir, "evaluation.json", CandidateEvaluationReport
        )

    def commit_shadow_validation(
        self, value: ShadowValidationReport
    ) -> ShadowValidationReport:
        return self._commit(
            self.shadow_validations_dir, value.report_id, "shadow-validation.json", value
        )

    def read_shadow_validation(self, report_id: str) -> ShadowValidationReport:
        return self._read(
            self.shadow_validations_dir,
            report_id,
            "shadow-validation.json",
            ShadowValidationReport,
        )

    def list_shadow_validations(self) -> list[ShadowValidationReport]:
        return self._list(
            self.shadow_validations_dir, "shadow-validation.json", ShadowValidationReport
        )

    def commit_approval(self, value: ReleaseApproval) -> ReleaseApproval:
        return self._commit(self.approvals_dir, value.approval_id, "approval.json", value)

    def read_approval(self, approval_id: str) -> ReleaseApproval:
        return self._read(self.approvals_dir, approval_id, "approval.json", ReleaseApproval)

    def list_approvals(self) -> list[ReleaseApproval]:
        return self._list(self.approvals_dir, "approval.json", ReleaseApproval)

    def commit_alias_update(self, value: AliasUpdateRecord) -> AliasUpdateRecord:
        return self._commit(
            self.alias_updates_dir, value.update_id, "alias-update.json", value
        )

    def read_alias_update(self, update_id: str) -> AliasUpdateRecord:
        return self._read(
            self.alias_updates_dir, update_id, "alias-update.json", AliasUpdateRecord
        )

    def list_alias_updates(self) -> list[AliasUpdateRecord]:
        return self._list(
            self.alias_updates_dir, "alias-update.json", AliasUpdateRecord
        )

    def commit_rollback(self, value: RollbackRecord) -> RollbackRecord:
        return self._commit(self.rollbacks_dir, value.rollback_id, "rollback.json", value)

    def list_rollbacks(self) -> list[RollbackRecord]:
        return self._list(self.rollbacks_dir, "rollback.json", RollbackRecord)

    def aliases(self) -> dict[ModelAlias, str]:
        self._validate_namespace(self.control_dir)
        path = self.control_dir / "aliases.json"
        if not path.exists():
            return {}
        if not path.is_file() or path.is_symlink():
            raise MLOpsStoreError("MLOps alias state is incomplete or unsafe")
        try:
            envelope = json.loads(path.read_bytes())
        except json.JSONDecodeError as exc:
            raise MLOpsStoreError("MLOps alias state is invalid JSON") from exc
        if not isinstance(envelope, dict) or set(envelope) != {"aliases", "semantic_sha256"}:
            raise MLOpsStoreError("MLOps alias envelope has an invalid shape")
        payload = envelope["aliases"]
        if not isinstance(payload, dict) or set(payload) - {item.value for item in ModelAlias}:
            raise MLOpsStoreError("MLOps alias state contains unknown aliases")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        if hashlib.sha256(canonical).hexdigest() != envelope["semantic_sha256"]:
            raise MLOpsStoreError("MLOps alias state checksum mismatch")
        result: dict[ModelAlias, str] = {}
        for key, candidate_id in payload.items():
            alias = ModelAlias(key)
            result[alias] = validate_safe_id(candidate_id)
            self.read_candidate(candidate_id)
        return result

    def update_aliases(self, aliases: dict[ModelAlias, str]) -> None:
        self._validate_namespace(self.control_dir)
        for candidate_id in aliases.values():
            self.read_candidate(candidate_id)
        payload = {
            alias.value: candidate_id
            for alias, candidate_id in sorted(aliases.items(), key=lambda item: item[0].value)
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        envelope = {
            "aliases": payload,
            "semantic_sha256": hashlib.sha256(canonical).hexdigest(),
        }
        raw = (json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n").encode()
        self._atomic_write(self.control_dir / "aliases.json", raw)

    @contextmanager
    def control_lock(
        self, *, timeout_seconds: float = 30.0, stale_seconds: float = 600.0
    ) -> Iterator[None]:
        with self._file_lock(
            self.locks_dir / "mlops-control.lock",
            timeout_seconds=timeout_seconds,
            stale_seconds=stale_seconds,
        ):
            yield

    @contextmanager
    def _file_lock(
        self, lock_path: Path, *, timeout_seconds: float, stale_seconds: float
    ) -> Iterator[None]:
        self._validate_namespace(self.locks_dir)
        if lock_path.is_symlink():
            raise MLOpsStoreError("MLOps control lock cannot be a symlink")
        deadline = time.monotonic() + timeout_seconds
        token = uuid.uuid4().hex
        fd: int | None = None
        while fd is None:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, f"pid={os.getpid()}\ntoken={token}\n".encode("ascii"))
                os.fsync(fd)
            except FileExistsError:
                if self._lock_is_abandoned(lock_path, stale_seconds=stale_seconds):
                    lock_path.unlink(missing_ok=True)
                    continue
                if time.monotonic() >= deadline:
                    raise MLOpsStoreError("timed out acquiring MLOps control lock")
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
        try:
            age = time.time() - lock_path.stat().st_mtime
        except FileNotFoundError:
            return False
        if age <= stale_seconds:
            return False
        try:
            payload = lock_path.read_text(encoding="ascii")
            pid_line = next(
                line for line in payload.splitlines() if line.startswith("pid=")
            )
            pid = int(pid_line.split("=", 1)[1])
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
        self._validate_namespace(namespace)
        final_dir = self._safe_child(namespace, safe_id)
        if final_dir.exists():
            existing = self._read(namespace, safe_id, filename, type(value))
            if getattr(existing, "semantic_digest")() != getattr(value, "semantic_digest")():
                raise MLOpsStoreError("immutable MLOps record conflicts with existing content")
            return existing
        raw = value.model_dump_json(indent=2).encode("utf-8") + b"\n"
        digest = hashlib.sha256(raw).hexdigest().encode("ascii") + b"\n"
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{safe_id}-", dir=namespace))
        try:
            (temp_dir / filename).write_bytes(raw)
            (temp_dir / f"{filename}.sha256").write_bytes(digest)
            self._fsync_path(temp_dir / filename)
            self._fsync_path(temp_dir / f"{filename}.sha256")
            try:
                os.rename(temp_dir, final_dir)
            except FileExistsError:
                existing = self._read(namespace, safe_id, filename, type(value))
                if getattr(existing, "semantic_digest")() != getattr(value, "semantic_digest")():
                    raise MLOpsStoreError("concurrent MLOps record content conflict")
                return existing
            self._fsync_dir(namespace)
        finally:
            if temp_dir.exists():
                for child in temp_dir.iterdir():
                    child.unlink(missing_ok=True)
                temp_dir.rmdir()
        return self._read(namespace, safe_id, filename, type(value))

    def _read(self, namespace: Path, identifier: str, filename: str, model: type[T]) -> T:
        safe_id = validate_safe_id(identifier)
        self._validate_namespace(namespace)
        directory = self._safe_child(namespace, safe_id)
        path = directory / filename
        digest_path = directory / f"{filename}.sha256"
        if not directory.exists():
            raise FileNotFoundError(safe_id)
        if directory.is_symlink() or not directory.is_dir():
            raise MLOpsStoreError("unsafe MLOps record directory")
        if not path.is_file() or path.is_symlink() or not digest_path.is_file():
            raise MLOpsStoreError("MLOps record is incomplete or unsafe")
        raw = path.read_bytes()
        expected = digest_path.read_text(encoding="ascii").strip()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise MLOpsStoreError("MLOps record checksum mismatch")
        try:
            return model.model_validate_json(raw)
        except Exception as exc:
            raise MLOpsStoreError("MLOps record failed schema validation") from exc

    def _list(self, namespace: Path, filename: str, model: type[T]) -> list[T]:
        self._validate_namespace(namespace)
        result: list[T] = []
        for child in sorted(namespace.iterdir()):
            if child.name.startswith("."):
                continue
            if child.is_symlink() or not child.is_dir():
                raise MLOpsStoreError("unsafe entry in MLOps namespace")
            result.append(self._read(namespace, child.name, filename, model))
        return result

    def _namespace(self, name: str) -> Path:
        path = self.root / name
        if path.is_symlink():
            raise ValueError("MLOps namespace cannot be a symlink")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _validate_namespace(self, namespace: Path) -> None:
        if self.root.is_symlink() or namespace.is_symlink():
            raise MLOpsStoreError("MLOps namespace was replaced by a symlink")
        try:
            namespace.resolve().relative_to(self.root.resolve())
        except ValueError as exc:
            raise MLOpsStoreError("MLOps namespace escaped its root") from exc
        if not namespace.is_dir():
            raise MLOpsStoreError("MLOps namespace is unavailable")

    @staticmethod
    def _safe_child(namespace: Path, identifier: str) -> Path:
        child = namespace / identifier
        try:
            child.resolve(strict=False).relative_to(namespace.resolve())
        except ValueError as exc:
            raise MLOpsStoreError("MLOps path escaped namespace") from exc
        return child

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            MLOpsStore._fsync_dir(path.parent)
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _fsync_path(path: Path) -> None:
        with path.open("rb") as handle:
            os.fsync(handle.fileno())

    @staticmethod
    def _fsync_dir(path: Path) -> None:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
