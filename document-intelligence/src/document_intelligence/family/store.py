from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from document_intelligence.exceptions import FamilyDetectionStoreCorruptError
from document_intelligence.family.models import FamilyDetectionResult
from document_intelligence.schema import validate_safe_id


class FamilyDetectionStore:
    def __init__(self, workspace: Path) -> None:
        self.root = workspace / "family-detections"
        self._assert_root_safe()
        self.root.mkdir(parents=True, exist_ok=True)

    def commit(self, result: FamilyDetectionResult) -> Path:
        detection_id = validate_safe_id(result.detection_id, field_name="detection_id")
        final_dir = self._safe_child(detection_id)
        if final_dir.exists():
            existing = self.read(detection_id)
            if existing.semantic_digest() != result.semantic_digest():
                raise FamilyDetectionStoreCorruptError(
                    "existing family detection identifier contains different output"
                )
            return final_dir
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{detection_id}.", dir=self.root))
        try:
            result_path = temp_dir / "result.json"
            self._atomic_json(result_path, result.model_dump(mode="json"))
            self._atomic_json(
                temp_dir / "manifest.json",
                {
                    "version": 1,
                    "status": "committed",
                    "detection_id": detection_id,
                    "document_id": result.document_id,
                    "parse_run_id": result.parse_run_id,
                    "source_document_digest": result.source_document_digest,
                    "structure_id": result.structure_id,
                    "source_structure_digest": result.source_structure_digest,
                    "detector_digest": result.detector_digest,
                    "semantic_digest": result.semantic_digest(),
                    "result_sha256": self._sha256_file(result_path),
                },
            )
            try:
                os.rename(temp_dir, final_dir)
            except OSError as exc:
                if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY} and not final_dir.exists():
                    raise
                self._remove_tree(temp_dir)
                existing = self.read(detection_id)
                if existing.semantic_digest() != result.semantic_digest():
                    raise FamilyDetectionStoreCorruptError(
                        "concurrent family detection commit produced different output"
                    ) from exc
        except Exception:
            self._remove_tree(temp_dir)
            raise
        return final_dir

    def read(self, detection_id: str) -> FamilyDetectionResult:
        safe_id = validate_safe_id(detection_id, field_name="detection_id")
        directory = self._safe_child(safe_id)
        if not directory.is_dir() or directory.is_symlink():
            raise FileNotFoundError(safe_id)
        try:
            manifest_path = self._safe_file(directory, "manifest.json")
            result_path = self._safe_file(directory, "result.json")
            manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("version") != 1 or manifest.get("status") != "committed":
                raise ValueError("unsupported or incomplete family detection manifest")
            if manifest.get("detection_id") != safe_id:
                raise ValueError("family detection manifest identifier mismatch")
            if manifest.get("result_sha256") != self._sha256_file(result_path):
                raise ValueError("family detection result digest mismatch")
            result = FamilyDetectionResult.model_validate_json(
                result_path.read_text(encoding="utf-8")
            )
            checks = {
                "detection_id": result.detection_id,
                "document_id": result.document_id,
                "parse_run_id": result.parse_run_id,
                "source_document_digest": result.source_document_digest,
                "structure_id": result.structure_id,
                "source_structure_digest": result.source_structure_digest,
                "detector_digest": result.detector_digest,
                "semantic_digest": result.semantic_digest(),
            }
            for field_name, actual in checks.items():
                if manifest.get(field_name) != actual:
                    raise ValueError(f"family detection manifest mismatch: {field_name}")
            return result
        except (FileNotFoundError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise FamilyDetectionStoreCorruptError(
                f"stored family detection {safe_id} failed integrity verification: {exc}"
            ) from exc

    def list_ids(self) -> list[str]:
        self._assert_root_safe()
        return sorted(
            item.name
            for item in self.root.iterdir()
            if item.is_dir() and not item.is_symlink() and not item.name.startswith(".")
        )

    def _safe_child(self, name: str) -> Path:
        self._assert_root_safe()
        target = self.root / name
        if target.parent.resolve() != self.root.resolve() or target.is_symlink():
            raise ValueError("family detection path is unsafe")
        return target


    def _assert_root_safe(self) -> None:
        if self.root.is_symlink():
            raise ValueError("family detection namespace cannot be a symlink")
        if self.root.exists() and not self.root.is_dir():
            raise ValueError("family detection namespace must be a directory")

    @staticmethod
    def _safe_file(directory: Path, name: str) -> Path:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"family detection artifact is missing or unsafe: {name}")
        return path

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _atomic_json(path: Path, payload: object) -> None:
        encoded = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
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

    @classmethod
    def _remove_tree(cls, path: Path) -> None:
        if not path.exists():
            return
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
            return
        for child in path.iterdir():
            cls._remove_tree(child)
        path.rmdir()
