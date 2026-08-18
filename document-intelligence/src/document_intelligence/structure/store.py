from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from document_intelligence.exceptions import StructureStoreCorruptError
from document_intelligence.schema import validate_safe_id
from document_intelligence.structure.models import StructureResult


class StructureStore:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.structures_dir = workspace / "structures"
        if self.structures_dir.is_symlink():
            raise ValueError("structure namespace cannot be a symbolic link")
        self.structures_dir.mkdir(parents=True, exist_ok=True)

    def commit(self, result: StructureResult) -> Path:
        structure_id = validate_safe_id(result.structure_id, field_name="structure_id")
        final_dir = self._safe_child(structure_id)
        if final_dir.exists():
            existing = self.read(structure_id)
            if existing.semantic_digest() != result.semantic_digest():
                raise StructureStoreCorruptError(
                    "existing structure identifier contains different semantic output"
                )
            return final_dir
        temp_dir = Path(
            tempfile.mkdtemp(prefix=f".{structure_id}.", dir=self.structures_dir)
        )
        try:
            result_path = temp_dir / "result.json"
            self._atomic_json(result_path, result.model_dump(mode="json"))
            self._atomic_json(
                temp_dir / "manifest.json",
                {
                    "version": 1,
                    "status": "committed",
                    "structure_id": structure_id,
                    "document_id": result.document_id,
                    "parse_run_id": result.parse_run_id,
                    "source_semantic_digest": result.source_semantic_digest,
                    "engine_digest": result.engine_digest,
                    "config_digest": result.config_digest,
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
                existing = self.read(structure_id)
                if existing.semantic_digest() != result.semantic_digest():
                    raise StructureStoreCorruptError(
                        "concurrent structure commit produced different output"
                    ) from exc
        except Exception:
            self._remove_tree(temp_dir)
            raise
        return final_dir

    def read(self, structure_id: str) -> StructureResult:
        safe_id = validate_safe_id(structure_id, field_name="structure_id")
        directory = self._safe_child(safe_id)
        if not directory.is_dir() or directory.is_symlink():
            raise FileNotFoundError(safe_id)
        try:
            manifest_path = self._safe_file(directory, "manifest.json")
            result_path = self._safe_file(directory, "result.json")
            manifest: dict[str, Any] = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
            if manifest.get("version") != 1 or manifest.get("status") != "committed":
                raise ValueError("unsupported or incomplete structure manifest")
            if manifest.get("structure_id") != safe_id:
                raise ValueError("structure manifest identifier mismatch")
            if manifest.get("result_sha256") != self._sha256_file(result_path):
                raise ValueError("structure result digest mismatch")
            result = StructureResult.model_validate_json(
                result_path.read_text(encoding="utf-8")
            )
            checks = {
                "structure_id": result.structure_id,
                "document_id": result.document_id,
                "parse_run_id": result.parse_run_id,
                "source_semantic_digest": result.source_semantic_digest,
                "engine_digest": result.engine_digest,
                "config_digest": result.config_digest,
                "semantic_digest": result.semantic_digest(),
            }
            for field_name, actual in checks.items():
                if manifest.get(field_name) != actual:
                    raise ValueError(f"structure manifest mismatch: {field_name}")
            return result
        except (
            FileNotFoundError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise StructureStoreCorruptError(
                f"stored structure {safe_id} failed integrity verification: {exc}"
            ) from exc

    def list_ids(self) -> list[str]:
        return sorted(
            item.name
            for item in self.structures_dir.iterdir()
            if item.is_dir() and not item.is_symlink() and not item.name.startswith(".")
        )

    def _safe_child(self, name: str) -> Path:
        target = self.structures_dir / name
        if target.parent.resolve() != self.structures_dir.resolve():
            raise ValueError("structure path escapes structure namespace")
        if target.is_symlink():
            raise ValueError("structure path cannot be a symbolic link")
        return target

    @staticmethod
    def _safe_file(directory: Path, name: str) -> Path:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"structure artifact is missing or unsafe: {name}")
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
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with temporary.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    @classmethod
    def _remove_tree(cls, path: Path) -> None:
        if not path.exists():
            return
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
            return
        for child in path.iterdir():
            cls._remove_tree(child)
        path.rmdir()
