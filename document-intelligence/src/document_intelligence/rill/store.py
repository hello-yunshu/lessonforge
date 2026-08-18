from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from document_intelligence.exceptions import RillStoreCorruptError
from document_intelligence.rill.models import (
    ShadowEvaluation,
    ShadowFeedbackRecord,
    ShadowResetRecord,
    ShadowSnapshotRecord,
)
from document_intelligence.schema import validate_safe_id

T = TypeVar("T", bound=BaseModel)


class RillShadowStore:
    def __init__(self, workspace: Path) -> None:
        self.root = workspace / "rill-shadow"
        if self.root.is_symlink():
            raise ValueError("Rill shadow namespace cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        self.evaluations_dir = self._namespace("evaluations")
        self.feedback_dir = self._namespace("feedback")
        self.snapshots_dir = self._namespace("snapshots")
        self.resets_dir = self._namespace("resets")

    def commit_evaluation(self, evaluation: ShadowEvaluation) -> ShadowEvaluation:
        return self._commit_model(
            self.evaluations_dir,
            evaluation.evaluation_id,
            "evaluation.json",
            evaluation,
            semantic_digest=evaluation.semantic_digest(),
        )

    def read_evaluation(self, evaluation_id: str) -> ShadowEvaluation:
        return self._read_model(
            self.evaluations_dir,
            evaluation_id,
            "evaluation.json",
            ShadowEvaluation,
            semantic_digest=lambda value: value.semantic_digest(),
        )

    def list_evaluations(self) -> list[ShadowEvaluation]:
        return self._list_models(self.evaluations_dir, self.read_evaluation)

    def evaluation_for_context(
        self,
        event_id: str,
        *,
        backend_name: str,
        model_generation: int,
        state_generation: int,
    ) -> ShadowEvaluation | None:
        safe_id = validate_safe_id(event_id, field_name="event_id")
        matches: list[ShadowEvaluation] = []
        for item in self.list_evaluations():
            if item.observe_event.event_id != safe_id or item.backend_name != backend_name:
                continue
            if item.rill_suggestion is not None:
                generation_matches = (
                    item.rill_suggestion.model_generation == model_generation
                    and item.rill_suggestion.state_generation == state_generation
                )
            else:
                generation_matches = (
                    item.input_model_generation == model_generation
                    and item.input_state_generation == state_generation
                )
            if generation_matches:
                matches.append(item)
        if len(matches) > 1:
            raise RillStoreCorruptError(
                "multiple Shadow evaluations reference one runtime context"
            )
        return matches[0] if matches else None

    def commit_feedback(self, feedback: ShadowFeedbackRecord) -> ShadowFeedbackRecord:
        return self._commit_model(
            self.feedback_dir,
            feedback.feedback_id,
            "feedback.json",
            feedback,
            semantic_digest=feedback.semantic_digest(),
        )

    def read_feedback(self, feedback_id: str) -> ShadowFeedbackRecord:
        return self._read_model(
            self.feedback_dir,
            feedback_id,
            "feedback.json",
            ShadowFeedbackRecord,
            semantic_digest=lambda value: value.semantic_digest(),
        )

    def list_feedback(self) -> list[ShadowFeedbackRecord]:
        return self._list_models(self.feedback_dir, self.read_feedback)

    def feedback_for_evaluation(self, evaluation_id: str) -> ShadowFeedbackRecord | None:
        safe_id = validate_safe_id(evaluation_id, field_name="evaluation_id")
        matches = [item for item in self.list_feedback() if item.evaluation_id == safe_id]
        if len(matches) > 1:
            raise RillStoreCorruptError("multiple final feedback records reference one evaluation")
        return matches[0] if matches else None

    def commit_snapshot(
        self,
        record: ShadowSnapshotRecord,
        *,
        state: str,
        drift_state: dict[str, Any],
    ) -> ShadowSnapshotRecord:
        snapshot_id = validate_safe_id(record.snapshot_id, field_name="snapshot_id")
        final_dir = self._safe_child(self.snapshots_dir, snapshot_id)
        state_bytes = state.encode("utf-8")
        if hashlib.sha256(state_bytes).hexdigest() != record.state_checksum:
            raise ValueError("snapshot state checksum differs from the record")
        drift_bytes = self._canonical_json(drift_state)
        if hashlib.sha256(drift_bytes).hexdigest() != record.drift_state_checksum:
            raise ValueError("snapshot drift-state checksum differs from the record")
        if final_dir.exists():
            existing, existing_state, existing_drift = self.read_snapshot(snapshot_id)
            existing_payload = existing.model_dump(mode="json", exclude={"created_at"})
            candidate_payload = record.model_dump(mode="json", exclude={"created_at"})
            if (
                existing_payload != candidate_payload
                or existing_state != state
                or existing_drift != drift_state
            ):
                raise RillStoreCorruptError("snapshot identifier contains different content")
            return existing
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{snapshot_id}.", dir=self.snapshots_dir))
        try:
            record_path = temp_dir / "record.json"
            state_path = temp_dir / "state.txt"
            drift_path = temp_dir / "drift-state.json"
            self._atomic_bytes(record_path, self._model_json(record))
            self._atomic_bytes(state_path, state_bytes)
            self._atomic_bytes(drift_path, drift_bytes)
            self._atomic_json(
                temp_dir / "manifest.json",
                {
                    "version": 1,
                    "kind": "rill-shadow-snapshot",
                    "id": snapshot_id,
                    "record_sha256": self._sha256_file(record_path),
                    "state_sha256": self._sha256_file(state_path),
                    "drift_state_sha256": self._sha256_file(drift_path),
                },
            )
            self._rename_commit(temp_dir, final_dir)
        except Exception:
            self._remove_tree(temp_dir)
            raise
        committed, committed_state, committed_drift = self.read_snapshot(snapshot_id)
        committed_payload = committed.model_dump(mode="json", exclude={"created_at"})
        candidate_payload = record.model_dump(mode="json", exclude={"created_at"})
        if (
            committed_payload != candidate_payload
            or committed_state != state
            or committed_drift != drift_state
        ):
            raise RillStoreCorruptError(
                "concurrent snapshot commit produced different semantic content"
            )
        return committed

    def read_snapshot(
        self, snapshot_id: str
    ) -> tuple[ShadowSnapshotRecord, str, dict[str, Any]]:
        safe_id = validate_safe_id(snapshot_id, field_name="snapshot_id")
        directory = self._safe_child(self.snapshots_dir, safe_id)
        if not directory.is_dir():
            raise FileNotFoundError(safe_id)
        try:
            manifest = self._read_manifest(directory, safe_id, kind="rill-shadow-snapshot")
            record_path = self._safe_file(directory, "record.json")
            state_path = self._safe_file(directory, "state.txt")
            drift_path = self._safe_file(directory, "drift-state.json")
            self._check_hash(record_path, manifest["record_sha256"])
            self._check_hash(state_path, manifest["state_sha256"])
            self._check_hash(drift_path, manifest["drift_state_sha256"])
            record = ShadowSnapshotRecord.model_validate_json(
                record_path.read_text(encoding="utf-8")
            )
            state = state_path.read_text(encoding="utf-8")
            drift_state = json.loads(drift_path.read_text(encoding="utf-8"))
            if hashlib.sha256(state.encode("utf-8")).hexdigest() != record.state_checksum:
                raise ValueError("snapshot state checksum mismatch")
            if self._sha256_file(drift_path) != record.drift_state_checksum:
                raise ValueError("snapshot drift-state checksum mismatch")
            return record, state, drift_state
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            raise RillStoreCorruptError(
                f"stored Rill snapshot {safe_id} failed integrity verification"
            ) from exc

    def commit_reset(self, record: ShadowResetRecord) -> ShadowResetRecord:
        semantic = hashlib.sha256(self._model_json(record, exclude_time=True)).hexdigest()
        return self._commit_model(
            self.resets_dir,
            record.reset_id,
            "reset.json",
            record,
            semantic_digest=semantic,
            exclude_time=True,
        )

    def list_resets(self) -> list[ShadowResetRecord]:
        def read(reset_id: str) -> ShadowResetRecord:
            return self._read_model(
                self.resets_dir,
                reset_id,
                "reset.json",
                ShadowResetRecord,
                semantic_digest=lambda value: hashlib.sha256(
                    self._model_json(value, exclude_time=True)
                ).hexdigest(),
            )

        return self._list_models(self.resets_dir, read)

    def _commit_model(
        self,
        namespace: Path,
        identifier: str,
        filename: str,
        model: T,
        *,
        semantic_digest: str,
        exclude_time: bool = False,
    ) -> T:
        safe_id = validate_safe_id(identifier)
        final_dir = self._safe_child(namespace, safe_id)
        if final_dir.exists():
            existing = self._read_model(
                namespace,
                safe_id,
                filename,
                type(model),
                semantic_digest=(
                    (lambda value: hashlib.sha256(
                        self._model_json(value, exclude_time=True)
                    ).hexdigest())
                    if exclude_time
                    else (lambda value: value.semantic_digest())
                ),
            )
            existing_digest = (
                hashlib.sha256(self._model_json(existing, exclude_time=True)).hexdigest()
                if exclude_time
                else existing.semantic_digest()
            )
            if existing_digest != semantic_digest:
                raise RillStoreCorruptError(
                    "Rill identifier already contains different semantic content"
                )
            return existing
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{safe_id}.", dir=namespace))
        try:
            model_path = temp_dir / filename
            self._atomic_bytes(model_path, self._model_json(model))
            self._atomic_json(
                temp_dir / "manifest.json",
                {
                    "version": 1,
                    "kind": namespace.name,
                    "id": safe_id,
                    "filename": filename,
                    "file_sha256": self._sha256_file(model_path),
                    "semantic_digest": semantic_digest,
                },
            )
            self._rename_commit(temp_dir, final_dir)
        except Exception:
            self._remove_tree(temp_dir)
            raise
        committed = self._read_model(
            namespace,
            safe_id,
            filename,
            type(model),
            semantic_digest=(
                (lambda value: hashlib.sha256(
                    self._model_json(value, exclude_time=True)
                ).hexdigest())
                if exclude_time
                else (lambda value: value.semantic_digest())
            ),
        )
        committed_digest = (
            hashlib.sha256(self._model_json(committed, exclude_time=True)).hexdigest()
            if exclude_time
            else committed.semantic_digest()
        )
        if committed_digest != semantic_digest:
            raise RillStoreCorruptError(
                "concurrent Rill commit produced different semantic content"
            )
        return committed

    def _read_model(
        self,
        namespace: Path,
        identifier: str,
        filename: str,
        model_type: type[T],
        *,
        semantic_digest: Any,
    ) -> T:
        safe_id = validate_safe_id(identifier)
        directory = self._safe_child(namespace, safe_id)
        if not directory.is_dir():
            raise FileNotFoundError(safe_id)
        try:
            manifest = self._read_manifest(directory, safe_id, kind=namespace.name)
            if manifest["filename"] != filename:
                raise ValueError("Rill manifest filename mismatch")
            model_path = self._safe_file(directory, filename)
            self._check_hash(model_path, manifest["file_sha256"])
            model = model_type.model_validate_json(model_path.read_text(encoding="utf-8"))
            if semantic_digest(model) != manifest["semantic_digest"]:
                raise ValueError("Rill semantic digest mismatch")
            return model
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            raise RillStoreCorruptError(
                f"stored Rill record {safe_id} failed integrity verification"
            ) from exc

    def _read_manifest(self, directory: Path, identifier: str, *, kind: str) -> dict[str, Any]:
        manifest_path = self._safe_file(directory, "manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("version") != 1 or manifest.get("id") != identifier:
            raise ValueError("Rill manifest identity mismatch")
        if manifest.get("kind") != kind:
            raise ValueError("Rill manifest namespace mismatch")
        return manifest

    def _list_models(self, namespace: Path, reader: Any) -> list[Any]:
        if self.root.is_symlink() or namespace.is_symlink():
            raise RillStoreCorruptError("Rill namespace cannot be a symbolic link")
        results = []
        for directory in sorted(namespace.iterdir()):
            if directory.name.startswith("."):
                continue
            if directory.is_symlink() or not directory.is_dir():
                raise RillStoreCorruptError("Rill namespace contains an invalid entry")
            results.append(reader(directory.name))
        return results

    def _namespace(self, name: str) -> Path:
        path = self.root / name
        if path.is_symlink():
            raise ValueError("Rill store namespace cannot be a symlink")
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _model_json(model: BaseModel, *, exclude_time: bool = False) -> bytes:
        payload = model.model_dump(mode="json")
        if exclude_time:
            payload.pop("created_at", None)
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @staticmethod
    def _canonical_json(payload: dict[str, Any]) -> bytes:
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        RillShadowStore._atomic_bytes(path, RillShadowStore._canonical_json(payload))

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
    def _rename_commit(temp_dir: Path, final_dir: Path) -> None:
        try:
            os.rename(temp_dir, final_dir)
        except OSError as exc:
            if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY} and not final_dir.exists():
                raise
            RillShadowStore._remove_tree(temp_dir)

    def _safe_child(self, parent: Path, name: str) -> Path:
        validate_safe_id(name)
        if self.root.is_symlink() or parent.is_symlink():
            raise RillStoreCorruptError("Rill namespace cannot be a symbolic link")
        trusted_root = self.root.resolve()
        namespace_root = parent.resolve()
        if namespace_root != trusted_root and trusted_root not in namespace_root.parents:
            raise RillStoreCorruptError("Rill namespace escapes the configured workspace")
        candidate = (parent / name).resolve()
        if namespace_root not in candidate.parents:
            raise ValueError("Rill identifier escapes its namespace")
        return candidate

    @staticmethod
    def _safe_file(directory: Path, filename: str) -> Path:
        path = directory / filename
        if path.is_symlink():
            raise ValueError("Rill artifacts cannot be symbolic links")
        root = directory.resolve()
        candidate = path.resolve()
        if root not in candidate.parents or not candidate.is_file():
            raise FileNotFoundError(filename)
        return candidate

    @staticmethod
    def _check_hash(path: Path, expected: str) -> None:
        if RillShadowStore._sha256_file(path) != expected:
            raise ValueError("Rill artifact digest mismatch")

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

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
