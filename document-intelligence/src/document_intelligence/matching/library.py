from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from document_intelligence.exceptions import StandardApprovalError, StandardStoreCorruptError
from document_intelligence.matching.fingerprint import (
    FINGERPRINT_VERSION,
    dhash,
    extract_orb,
    image_sha256,
    layout_digest,
    page_text,
    text_ngram_hashes,
)
from document_intelligence.matching.models import PageFingerprint, StandardDocumentManifest
from document_intelligence.parser_sdk.utils import stable_id
from document_intelligence.schema import ParsedDocument
from document_intelligence.services.store import ArtifactStore


def _load_pymupdf() -> Any:
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "PDF pixel rendering is disabled because the optional PyMuPDF renderer "
            "is not installed or qualified"
        ) from exc
    return fitz


class StandardLibrary:
    def __init__(
        self,
        store: ArtifactStore,
        *,
        render_dpi: int = 144,
        max_render_pixels: int = 50_000_000,
        pdf_render_backend: str = "pymupdf",
    ) -> None:
        self.store = store
        self.root = store.standard_dir
        self.documents_dir = self.root / "documents"
        self.index_path = self.root / "page-index.json"
        self.render_dpi = render_dpi
        self.max_render_pixels = max_render_pixels
        self.pdf_render_backend = pdf_render_backend
        fingerprint_source = (Path(__file__).parent / "fingerprint.py").read_bytes()
        pipeline_material = (
            fingerprint_source
            + b"\0"
            + FINGERPRINT_VERSION.encode("utf-8")
            + b"\0"
            + cv2.__version__.encode("utf-8")
            + b"\0"
            + str(render_dpi).encode("ascii")
        )
        self.fingerprint_pipeline_digest = hashlib.sha256(pipeline_material).hexdigest()
        self.documents_dir.mkdir(parents=True, exist_ok=True)

    def register_run(
        self,
        run_id: str,
        *,
        reviewer: str,
        approval_note: str,
        approved: bool,
    ) -> StandardDocumentManifest:
        if not approved:
            raise StandardApprovalError("explicit approval is required for standard registration")
        if not reviewer.strip() or not approval_note.strip():
            raise StandardApprovalError("reviewer and approval_note are required")
        result = self.store.read_result(run_id)
        source_ref = result.document.source.source_ref
        if not source_ref:
            raise StandardApprovalError("run has no retained source artifact")
        if not result.run.semantic_output_digest:
            raise StandardApprovalError("run has no semantic output digest")
        standard_id = stable_id(
            "std",
            result.document.source.sha256,
            result.run.semantic_output_digest,
            result.document.schema_version,
            self.fingerprint_pipeline_digest,
        )
        target = self.documents_dir / standard_id
        if target.exists():
            self.rebuild_index()
            return self.read_manifest(standard_id)

        source_bytes = self.store.read_source(source_ref)
        ordered_pages = sorted(result.document.pages, key=lambda page: page.index)
        if [page.index for page in ordered_pages] != list(range(len(ordered_pages))):
            raise StandardApprovalError("standard document page indexes are not contiguous")
        rendered_pages = self._iter_rendered_pages(
            source_bytes,
            result.document.source.mime_type,
            expected_pages=len(ordered_pages),
            scale=self.render_dpi / 72.0,
        )
        temp_dir = Path(tempfile.mkdtemp(prefix=f".{standard_id}.", dir=self.documents_dir))
        try:
            page_dir = temp_dir / "pages"
            thumb_dir = temp_dir / "thumbnails"
            feature_dir = temp_dir / "features"
            page_dir.mkdir()
            thumb_dir.mkdir()
            feature_dir.mkdir()
            fingerprints: list[PageFingerprint] = []
            page_pairs = zip(ordered_pages, rendered_pages, strict=True)
            for position, (page, rendered) in enumerate(page_pairs):
                rendered_index, image = rendered
                if rendered_index != page.index:
                    raise StandardApprovalError(
                        f"rendered page index {rendered_index} != parsed page index {page.index}"
                    )
                image_ref = (
                    Path("standard")
                    / "documents"
                    / standard_id
                    / "pages"
                    / f"{page.page_id}.png"
                )
                thumb_ref = (
                    Path("standard")
                    / "documents"
                    / standard_id
                    / "thumbnails"
                    / f"{page.page_id}.jpg"
                )
                feature_ref = (
                    Path("standard")
                    / "documents"
                    / standard_id
                    / "features"
                    / f"{page.page_id}.npz"
                )
                self._write_image(page_dir / f"{page.page_id}.png", image, ".png")
                thumbnail = self._thumbnail(image)
                self._write_image(thumb_dir / f"{page.page_id}.jpg", thumbnail, ".jpg")
                points, descriptors = extract_orb(image)
                feature_path = feature_dir / f"{page.page_id}.npz"
                np.savez_compressed(
                    feature_path,
                    keypoints=points,
                    descriptors=descriptors,
                    width=np.array([image.shape[1]], dtype=np.int32),
                    height=np.array([image.shape[0]], dtype=np.int32),
                )
                normalized = page_text(page, result.document.elements)
                fingerprints.append(
                    PageFingerprint(
                        standard_id=standard_id,
                        fingerprint_version=FINGERPRINT_VERSION,
                        document_id=result.document.document_id,
                        page_id=page.page_id,
                        page_index=page.index,
                        source_sha256=result.document.source.sha256,
                        page_image_sha256=image_sha256(image),
                        thumbnail_sha256=self._sha256_file(
                            thumb_dir / f"{page.page_id}.jpg"
                        ),
                        feature_sha256=self._sha256_file(feature_path),
                        perceptual_hash=dhash(image),
                        normalized_text=normalized,
                        text_ngram_hashes=text_ngram_hashes(normalized),
                        layout_digest=layout_digest(page, result.document.elements),
                        width=int(image.shape[1]),
                        height=int(image.shape[0]),
                        page_image_ref=image_ref.as_posix(),
                        thumbnail_ref=thumb_ref.as_posix(),
                        feature_ref=feature_ref.as_posix(),
                        keypoint_count=int(len(points)),
                        previous_page_id=(
                            ordered_pages[position - 1].page_id if position else None
                        ),
                        next_page_id=(
                            ordered_pages[position + 1].page_id
                            if position + 1 < len(ordered_pages)
                            else None
                        ),
                    )
                )
            document_ref = (
                Path("standard") / "documents" / standard_id / "document.json"
            ).as_posix()
            document_path = temp_dir / "document.json"
            self._atomic_json(document_path, result.document.model_dump(mode="json"))
            manifest = StandardDocumentManifest(
                standard_id=standard_id,
                fingerprint_version=FINGERPRINT_VERSION,
                fingerprint_pipeline_digest=self.fingerprint_pipeline_digest,
                render_dpi=self.render_dpi,
                document_id=result.document.document_id,
                source_sha256=result.document.source.sha256,
                semantic_output_digest=result.run.semantic_output_digest,
                schema_version=result.document.schema_version,
                source_ref=source_ref,
                document_ref=document_ref,
                document_sha256=self._sha256_file(document_path),
                reviewer=reviewer.strip(),
                approval_note=approval_note.strip(),
                approved_at=datetime.now(timezone.utc),
                page_fingerprints=fingerprints,
            )
            self._atomic_json(temp_dir / "manifest.json", manifest.model_dump(mode="json"))
            try:
                os.rename(temp_dir, target)
            except OSError:
                if not target.exists():
                    raise
                self._remove_tree(temp_dir)
            self.rebuild_index()
            return self.read_manifest(standard_id)
        except Exception:
            self._remove_tree(temp_dir)
            raise

    def rebuild_index(self) -> None:
        with self._index_lock():
            pages: list[dict[str, object]] = []
            manifest_records = self._manifest_records()
            for standard_id, _ in manifest_records:
                manifest = self.read_manifest(standard_id)
                pages.extend(
                    item.model_dump(mode="json") for item in manifest.page_fingerprints
                )
            self._atomic_json(
                self.index_path,
                {
                    "version": 3,
                    "fingerprint_version": FINGERPRINT_VERSION,
                    "fingerprint_pipeline_digest": self.fingerprint_pipeline_digest,
                    "manifest_set_digest": self._manifest_set_digest(manifest_records),
                    "pages": pages,
                },
            )

    def load_page_index(self) -> list[PageFingerprint]:
        if not self.index_path.is_file():
            return []
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            if payload.get("version") != 3:
                raise ValueError("unsupported standard page index version")
            if payload.get("fingerprint_version") != FINGERPRINT_VERSION:
                raise ValueError("standard page index fingerprint version mismatch")
            if payload.get("fingerprint_pipeline_digest") != self.fingerprint_pipeline_digest:
                raise ValueError("standard page index pipeline digest mismatch")
            manifest_records = self._manifest_records()
            if payload.get("manifest_set_digest") != self._manifest_set_digest(
                manifest_records
            ):
                raise ValueError("standard page index is stale or missing manifests")
            pages = [
                PageFingerprint.model_validate(item) for item in payload.get("pages", [])
            ]
        except Exception as exc:
            raise StandardStoreCorruptError(f"invalid standard page index: {exc}") from exc
        return pages

    def list_manifests(self) -> list[StandardDocumentManifest]:
        manifests: list[StandardDocumentManifest] = []
        try:
            for standard_id, _ in self._manifest_records():
                manifests.append(self.read_manifest(standard_id))
        except Exception as exc:
            raise StandardStoreCorruptError(f"invalid standard manifest: {exc}") from exc
        return manifests

    def read_manifest(self, standard_id: str) -> StandardDocumentManifest:
        from document_intelligence.schema import validate_safe_id

        validate_safe_id(standard_id, field_name="standard_id")
        path = self._standard_file(standard_id, "manifest.json")
        try:
            manifest = StandardDocumentManifest.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            if manifest.fingerprint_version != FINGERPRINT_VERSION:
                raise ValueError("standard manifest fingerprint version is incompatible")
            if manifest.fingerprint_pipeline_digest != self.fingerprint_pipeline_digest:
                raise ValueError("standard manifest fingerprint pipeline is incompatible")
            if manifest.render_dpi != self.render_dpi:
                raise ValueError("standard manifest render DPI is incompatible")
            return manifest
        except Exception as exc:
            raise StandardStoreCorruptError(
                f"invalid standard manifest for {standard_id}: {exc}"
            ) from exc

    def read_document(self, standard_id: str) -> ParsedDocument:
        from document_intelligence.schema import validate_safe_id

        validate_safe_id(standard_id, field_name="standard_id")
        path = self._standard_file(standard_id, "document.json")
        try:
            manifest = self.read_manifest(standard_id)
            if self._sha256_file(path) != manifest.document_sha256:
                raise ValueError("standard document file digest mismatch")
            document = ParsedDocument.model_validate_json(path.read_text(encoding="utf-8"))
            if document.document_id != manifest.document_id:
                raise ValueError("standard document identifier mismatch")
            if document.source.sha256 != manifest.source_sha256:
                raise ValueError("standard document source digest mismatch")
            if document.source.source_ref != manifest.source_ref:
                raise ValueError("standard document source reference mismatch")
            if document.schema_version != manifest.schema_version:
                raise ValueError("standard document schema version mismatch")
            if document.semantic_digest() != manifest.semantic_output_digest:
                raise ValueError("standard document semantic digest mismatch")
            return document
        except Exception as exc:
            raise StandardStoreCorruptError(
                f"invalid standard document for {standard_id}: {exc}"
            ) from exc

    def read_image(
        self, ref: str, *, expected_pixel_sha256: str | None = None
    ) -> np.ndarray:
        path = self._resolve_standard_ref(ref)
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise StandardStoreCorruptError(f"unable to decode standard image: {ref}")
        if expected_pixel_sha256 is not None and image_sha256(image) != expected_pixel_sha256:
            raise StandardStoreCorruptError(f"standard image pixel digest mismatch: {ref}")
        return image

    def load_features(
        self, ref: str, *, expected_sha256: str
    ) -> tuple[np.ndarray, np.ndarray, int, int]:
        path = self._resolve_standard_ref(ref)
        try:
            if self._sha256_file(path) != expected_sha256:
                raise ValueError("feature file digest mismatch")
            with np.load(path, allow_pickle=False) as data:
                points = data["keypoints"].astype(np.float32)
                descriptors = data["descriptors"].astype(np.uint8)
                width = int(data["width"][0])
                height = int(data["height"][0])
            if points.ndim != 2 or points.shape[1:] != (2,):
                raise ValueError("keypoints must have shape (n, 2)")
            if descriptors.ndim != 2 or descriptors.shape[1:] != (32,):
                raise ValueError("ORB descriptors must have shape (n, 32)")
            if len(points) != len(descriptors) or width <= 0 or height <= 0:
                raise ValueError("feature dimensions are inconsistent")
            return points, descriptors, width, height
        except StandardStoreCorruptError:
            raise
        except Exception as exc:
            raise StandardStoreCorruptError(f"invalid standard feature file {ref}: {exc}") from exc


    def _standard_file(self, standard_id: str, filename: str) -> Path:
        from document_intelligence.schema import validate_safe_id

        validate_safe_id(standard_id, field_name="standard_id")
        standard_dir = self.documents_dir / standard_id
        raw_path = standard_dir / filename
        if standard_dir.is_symlink() or raw_path.is_symlink():
            raise StandardStoreCorruptError("standard files cannot be symbolic links")
        candidate = raw_path.resolve()
        root = self.documents_dir.resolve()
        if root not in candidate.parents or not candidate.is_file():
            raise FileNotFoundError(standard_id)
        return candidate

    def _manifest_records(self) -> list[tuple[str, str]]:
        records: list[tuple[str, str]] = []
        for child in sorted(self.documents_dir.iterdir(), key=lambda item: item.name):
            if child.name.startswith("."):
                continue
            if child.is_symlink() or not child.is_dir():
                raise StandardStoreCorruptError(
                    f"unexpected standard document entry: {child.name}"
                )
            from document_intelligence.schema import validate_safe_id

            try:
                validate_safe_id(child.name, field_name="standard_id")
            except ValueError as exc:
                raise StandardStoreCorruptError(str(exc)) from exc
            manifest_path = self._standard_file(child.name, "manifest.json")
            records.append((child.name, self._sha256_file(manifest_path)))
        return records

    @staticmethod
    def _manifest_set_digest(records: list[tuple[str, str]]) -> str:
        payload = json.dumps(records, separators=(",", ":"), ensure_ascii=True).encode(
            "utf-8"
        )
        return hashlib.sha256(payload).hexdigest()

    @contextmanager
    def _index_lock(
        self, *, timeout_seconds: float = 10.0, stale_seconds: float = 1800.0
    ) -> Iterator[None]:
        lock_path = self.root / ".page-index.lock"
        deadline = time.monotonic() + timeout_seconds
        token = uuid.uuid4().hex
        fd: int | None = None
        while fd is None:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                payload = f"pid={os.getpid()}\ntoken={token}\n".encode("ascii")
                os.write(fd, payload)
                os.fsync(fd)
            except FileExistsError:
                try:
                    if self._lock_is_abandoned(lock_path, stale_seconds=stale_seconds):
                        lock_path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise StandardStoreCorruptError(
                        "timed out acquiring standard page-index lock"
                    )
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
            pid_line = next(
                line for line in payload.splitlines() if line.startswith("pid=")
            )
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

    def _resolve_standard_ref(self, ref: str) -> Path:
        candidate = (self.store.workspace / ref).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("standard reference escapes namespace")
        if not candidate.is_file():
            raise FileNotFoundError(ref)
        return candidate

    def _iter_rendered_pages(
        self, source: bytes, mime_type: str, *, expected_pages: int, scale: float
    ) -> Iterator[tuple[int, np.ndarray]]:
        if mime_type == "application/pdf":
            if self.pdf_render_backend != "pymupdf":
                raise StandardApprovalError(
                    "PDF standard rendering is disabled by deployment policy"
                )
            fitz = _load_pymupdf()
            document = fitz.open(stream=source, filetype="pdf")
            try:
                if document.needs_pass:
                    raise StandardApprovalError("encrypted PDF cannot become a standard document")
                if document.page_count != expected_pages:
                    raise StandardApprovalError(
                        f"rendered page count {document.page_count} "
                        f"!= parsed page count {expected_pages}"
                    )
                matrix = fitz.Matrix(scale, scale)
                for page_index, page in enumerate(document):
                    width = max(1, round(page.rect.width * scale))
                    height = max(1, round(page.rect.height * scale))
                    pixels = width * height
                    if pixels > self.max_render_pixels:
                        raise StandardApprovalError(
                            f"page {page_index} render exceeds pixel limit: "
                            f"{pixels} > {self.max_render_pixels}"
                        )
                    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                    array = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                        pixmap.height, pixmap.width, pixmap.n
                    )
                    if pixmap.n == 3:
                        array = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
                    else:
                        array = cv2.cvtColor(array, cv2.COLOR_RGBA2BGR)
                    yield page_index, array
            finally:
                document.close()
            return
        if mime_type.startswith("image/"):
            with Image.open(BytesIO(source)) as image:
                width, height = image.size
                if width * height > self.max_render_pixels:
                    raise StandardApprovalError(
                        f"standard image exceeds pixel limit: {width * height} > "
                        f"{self.max_render_pixels}"
                    )
                rgb = np.array(image.convert("RGB"))
            if expected_pages != 1:
                raise StandardApprovalError(
                    f"rendered page count 1 != parsed page count {expected_pages}"
                )
            yield 0, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            return
        raise StandardApprovalError(f"unsupported standard source MIME: {mime_type}")

    @staticmethod
    def _thumbnail(image: np.ndarray, max_side: int = 512) -> np.ndarray:
        height, width = image.shape[:2]
        scale = min(1.0, max_side / max(height, width))
        if scale == 1.0:
            return image.copy()
        return cv2.resize(
            image,
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    @staticmethod
    def _write_image(path: Path, image: np.ndarray, suffix: str) -> None:
        ok, encoded = cv2.imencode(suffix, image)
        if not ok:
            raise RuntimeError(f"unable to encode {suffix} image")
        path.write_bytes(encoded.tobytes())

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
