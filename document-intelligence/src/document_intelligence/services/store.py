from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from document_intelligence.exceptions import RunStoreCorruptError
from document_intelligence.schema import ParserResult, ParseRequest, validate_safe_id


class ArtifactStore:
    """Content-addressed source/asset store and atomic run store.

    Standard results live under a separate namespace and are only written by the Phase 2
    ``StandardLibrary``. Parser runs have no code path that writes there.
    """

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.runs_dir = workspace / "runs"
        self.raw_dir = workspace / "raw"  # retained for Phase 1 layout compatibility
        self.sources_dir = workspace / "sources"
        self.assets_dir = workspace / "assets"
        self.standard_dir = workspace / "standard"
        for path in (
            self.runs_dir,
            self.raw_dir,
            self.sources_dir,
            self.assets_dir,
            self.standard_dir,
        ):
            if path.is_symlink():
                raise ValueError(f"artifact namespace cannot be a symbolic link: {path}")
            path.mkdir(parents=True, exist_ok=True)

    def commit_success(self, request: ParseRequest, result: ParserResult) -> Path:
        run_id = validate_safe_id(result.run.parse_run_id, field_name="parse_run_id")
        final_dir = self._safe_child(self.runs_dir, run_id)
        if final_dir.exists():
            self._assert_existing_equivalent(final_dir, result)
            return final_dir

        source_ref = self._store_source(request)
        for digest, content in result.binary_artifacts.items():
            self._store_asset(digest, content)

        stored_result = result.model_copy(deep=True)
        stored_result.document.source.source_ref = source_ref
        raw_ref = f"runs/{run_id}/raw.json"
        for item in stored_result.document.evidence:
            item.raw_output_ref = raw_ref
        if stored_result.document.semantic_digest() != stored_result.run.semantic_output_digest:
            raise RuntimeError("storage metadata changed semantic output digest")

        temp_dir = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=self.runs_dir))
        try:
            raw_payload = stored_result.raw_output
            self._atomic_json(temp_dir / "raw.json", raw_payload)
            run_payload = stored_result.run.model_dump(mode="json")
            document_payload = stored_result.document.model_dump(mode="json")
            run_path = temp_dir / "run.json"
            document_path = temp_dir / "document.json"
            raw_path = temp_dir / "raw.json"
            self._atomic_json(run_path, run_payload)
            self._atomic_json(document_path, document_payload)
            self._atomic_json(
                temp_dir / "manifest.json",
                {
                    "version": 2,
                    "parse_run_id": run_id,
                    "semantic_output_digest": stored_result.run.semantic_output_digest,
                    "parser_digest": stored_result.run.parser_digest,
                    "request_context_digest": stored_result.run.request_context_digest,
                    "source_ref": source_ref,
                    "source_sha256": request.sha256,
                    "raw_output_ref": raw_ref,
                    "raw_output_sha256": self._sha256_file(raw_path),
                    "run_sha256": self._sha256_file(run_path),
                    "document_sha256": self._sha256_file(document_path),
                    "status": "committed",
                },
            )
            try:
                os.rename(temp_dir, final_dir)
            except OSError as exc:
                if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY} and not final_dir.exists():
                    raise
                self._remove_tree(temp_dir)
                self._assert_existing_equivalent(final_dir, stored_result)
        except Exception:
            self._remove_tree(temp_dir)
            raise
        return final_dir

    def record_failure(self, run_id: str, payload: dict[str, Any]) -> Path:
        safe_id = validate_safe_id(run_id, field_name="failure_id")
        target = self._safe_child(self.runs_dir, f"{safe_id}.failed.json")
        self._atomic_json(target, payload)
        return target

    def read_result(self, run_id: str) -> ParserResult:
        safe_id = validate_safe_id(run_id, field_name="parse_run_id")
        run_dir = self._safe_child(self.runs_dir, safe_id)
        if not run_dir.is_dir():
            raise FileNotFoundError(run_id)
        try:
            manifest_path = self._run_file(run_dir, "manifest.json")
            run_path = self._run_file(run_dir, "run.json")
            document_path = self._run_file(run_dir, "document.json")
            raw_path = self._run_file(run_dir, "raw.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("version") != 2 or manifest.get("status") != "committed":
                raise ValueError("unsupported or incomplete run manifest")
            if manifest.get("parse_run_id") != safe_id:
                raise ValueError("run manifest identifier mismatch")
            expected_files = {
                "run_sha256": run_path,
                "document_sha256": document_path,
                "raw_output_sha256": raw_path,
            }
            for field_name, path in expected_files.items():
                if manifest.get(field_name) != self._sha256_file(path):
                    raise ValueError(f"run artifact digest mismatch: {field_name}")
            source_ref = str(manifest.get("source_ref", ""))
            source_path = self._resolve_relative_ref(
                source_ref, expected_root=self.sources_dir
            )
            if manifest.get("source_sha256") != self._sha256_file(source_path):
                raise ValueError("retained source digest mismatch")
            document = json.loads(document_path.read_text(encoding="utf-8"))
            run = json.loads(run_path.read_text(encoding="utf-8"))
            raw_output = json.loads(raw_path.read_text(encoding="utf-8"))
            result = ParserResult.model_validate(
                {"document": document, "run": run, "raw_output": raw_output}
            )
            if result.document.source.source_ref != source_ref:
                raise ValueError("document source reference differs from run manifest")
            if result.run.semantic_output_digest != manifest.get("semantic_output_digest"):
                raise ValueError("semantic output digest differs from run manifest")
            if result.document.semantic_digest() != result.run.semantic_output_digest:
                raise ValueError("stored document semantic digest mismatch")
            if result.run.parser_digest != manifest.get("parser_digest"):
                raise ValueError("parser digest differs from run manifest")
            if result.run.request_context_digest != manifest.get("request_context_digest"):
                raise ValueError("request context digest differs from run manifest")
            return result
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RunStoreCorruptError(
                f"stored run {safe_id} failed integrity verification: {exc}"
            ) from exc

    def read_source(self, source_ref: str) -> bytes:
        target = self._resolve_relative_ref(source_ref, expected_root=self.sources_dir)
        return target.read_bytes()

    def resolve_asset(self, asset_ref: str) -> Path:
        if not asset_ref.startswith("sha256:"):
            raise ValueError("unsupported asset reference")
        digest = asset_ref.removeprefix("sha256:")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("invalid asset digest")
        target = self.assets_dir / digest[:2] / f"{digest}.bin"
        if not target.is_file():
            raise FileNotFoundError(asset_ref)
        return target

    def standard_snapshot(self) -> list[str]:
        return sorted(
            str(item.relative_to(self.standard_dir))
            for item in self.standard_dir.rglob("*")
            if item.is_file()
        )

    def _store_source(self, request: ParseRequest) -> str:
        suffix = {
            "application/pdf": ".pdf",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
        }.get(request.mime_type, ".bin")
        relative = Path("sources") / request.sha256[:2] / f"{request.sha256}{suffix}"
        target = self.workspace / relative
        self._write_content_addressed(target, request.content, request.sha256)
        return relative.as_posix()

    def _store_asset(self, digest: str, content: bytes) -> str:
        actual = hashlib.sha256(content).hexdigest()
        if digest != actual:
            raise ValueError(f"binary artifact digest mismatch: expected {digest}, got {actual}")
        relative = Path("assets") / digest[:2] / f"{digest}.bin"
        target = self.workspace / relative
        self._write_content_addressed(target, content, digest)
        return relative.as_posix()

    def _write_content_addressed(self, path: Path, content: bytes, digest: str) -> None:
        if path.exists():
            if self._sha256_file(path) != digest:
                raise RuntimeError(f"content-addressed artifact corrupted: {path}")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if hashlib.sha256(Path(temp_name).read_bytes()).hexdigest() != digest:
                raise RuntimeError("temporary content digest mismatch")
            try:
                os.link(temp_name, path)
            except FileExistsError:
                if self._sha256_file(path) != digest:
                    raise RuntimeError(f"content-addressed artifact collision: {path}")
            finally:
                Path(temp_name).unlink(missing_ok=True)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise

    def _assert_existing_equivalent(self, final_dir: Path, result: ParserResult) -> None:
        if not final_dir.is_dir():
            raise RuntimeError(f"run path exists but is not a directory: {final_dir}")
        existing = self.read_result(final_dir.name)
        if existing.run.semantic_output_digest != result.run.semantic_output_digest:
            raise RuntimeError("same run_id produced a different semantic output")
        if existing.run.parser_digest != result.run.parser_digest:
            raise RuntimeError("same run_id produced a different parser digest")

    def _resolve_relative_ref(self, ref: str, *, expected_root: Path) -> Path:
        candidate = (self.workspace / ref).resolve()
        root = expected_root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("artifact reference escapes its namespace")
        if not candidate.is_file():
            raise FileNotFoundError(ref)
        return candidate

    @staticmethod
    def _safe_child(parent: Path, name: str) -> Path:
        if "/" in name or "\\" in name or name in {".", ".."}:
            raise ValueError("unsafe artifact identifier")
        root = parent.resolve()
        candidate = (parent / name).resolve()
        if root not in candidate.parents:
            raise ValueError("artifact identifier escapes its namespace")
        return candidate

    @staticmethod
    def _run_file(run_dir: Path, filename: str) -> Path:
        raw_path = run_dir / filename
        if raw_path.is_symlink():
            raise ValueError("run artifacts cannot be symbolic links")
        candidate = raw_path.resolve()
        root = run_dir.resolve()
        if root not in candidate.parents or not candidate.is_file():
            raise FileNotFoundError(filename)
        return candidate

    @staticmethod
    def _atomic_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise

    @staticmethod
    def _sha256_file(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _remove_tree(path: Path) -> None:
        if not path.exists():
            return
        for item in sorted(path.rglob("*"), key=lambda value: len(value.parts), reverse=True):
            if item.is_file() or item.is_symlink():
                item.unlink(missing_ok=True)
            else:
                item.rmdir()
        path.rmdir()
