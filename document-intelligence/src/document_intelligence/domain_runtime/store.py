from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from document_intelligence.domain_runtime.models import DomainResult
from document_intelligence.exceptions import DomainResultStoreCorruptError
from document_intelligence.schema import validate_safe_id


class DomainResultStore:
    def __init__(self, workspace: Path) -> None:
        self.root = workspace / "domain-results"
        if self.root.is_symlink():
            raise ValueError("domain result namespace cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)

    def commit(self, result: DomainResult) -> Path:
        result_id = validate_safe_id(result.domain_result_id, field_name="domain_result_id")
        final_dir = self._safe_child(result_id)
        if final_dir.exists():
            existing = self.read(result_id)
            if existing.semantic_digest() != result.semantic_digest():
                raise DomainResultStoreCorruptError(
                    "existing domain result identifier contains different semantic output"
                )
            return final_dir
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{result_id}.", dir=self.root))
        try:
            result_path = temp_dir / "result.json"
            self._atomic_json(result_path, result.model_dump(mode="json"))
            self._atomic_json(
                temp_dir / "manifest.json",
                {
                    "version": 1,
                    "status": "committed",
                    "domain_result_id": result_id,
                    "structure_id": result.structure_id,
                    "source_structure_digest": result.source_structure_digest,
                    "document_id": result.document_id,
                    "parse_run_id": result.parse_run_id,
                    "pack_id": result.pack_id,
                    "pack_version": result.pack_version,
                    "pack_digest": result.pack_digest,
                    "runtime_digest": result.runtime_digest,
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
                existing = self.read(result_id)
                if existing.semantic_digest() != result.semantic_digest():
                    raise DomainResultStoreCorruptError(
                        "concurrent domain result commit produced different output"
                    ) from exc
        except Exception:
            self._remove_tree(temp_dir)
            raise
        return final_dir

    def read(self, result_id: str) -> DomainResult:
        safe_id = validate_safe_id(result_id, field_name="domain_result_id")
        directory = self._safe_child(safe_id)
        if not directory.is_dir() or directory.is_symlink():
            raise FileNotFoundError(safe_id)
        try:
            manifest_path = self._safe_file(directory, "manifest.json")
            result_path = self._safe_file(directory, "result.json")
            manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("version") != 1 or manifest.get("status") != "committed":
                raise ValueError("unsupported or incomplete domain result manifest")
            if manifest.get("domain_result_id") != safe_id:
                raise ValueError("domain result manifest identifier mismatch")
            if manifest.get("result_sha256") != self._sha256_file(result_path):
                raise ValueError("domain result file digest mismatch")
            result = DomainResult.model_validate_json(result_path.read_text(encoding="utf-8"))
            checks = {
                "domain_result_id": result.domain_result_id,
                "structure_id": result.structure_id,
                "source_structure_digest": result.source_structure_digest,
                "document_id": result.document_id,
                "parse_run_id": result.parse_run_id,
                "pack_id": result.pack_id,
                "pack_version": result.pack_version,
                "pack_digest": result.pack_digest,
                "runtime_digest": result.runtime_digest,
                "semantic_digest": result.semantic_digest(),
            }
            for field_name, actual in checks.items():
                if manifest.get(field_name) != actual:
                    raise ValueError(f"domain result manifest mismatch: {field_name}")
            return result
        except (ValueError, TypeError, json.JSONDecodeError, FileNotFoundError) as exc:
            raise DomainResultStoreCorruptError(
                f"stored domain result {safe_id} failed integrity verification: {exc}"
            ) from exc

    def list_ids(self) -> list[str]:
        return sorted(
            item.name
            for item in self.root.iterdir()
            if item.is_dir() and not item.is_symlink() and not item.name.startswith(".")
        )

    def _safe_child(self, name: str) -> Path:
        path = (self.root / name).resolve()
        root = self.root.resolve()
        if root not in path.parents:
            raise ValueError("domain result path escapes namespace")
        if path.is_symlink():
            raise ValueError("domain result path cannot be a symlink")
        return path

    @staticmethod
    def _safe_file(directory: Path, name: str) -> Path:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"domain result artifact is missing or unsafe: {name}")
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
