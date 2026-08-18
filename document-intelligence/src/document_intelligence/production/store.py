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

from document_intelligence.exceptions import ProductionStoreCorruptError
from document_intelligence.schema import validate_safe_id

from .models import (
    DatasetQualificationEvidence,
    LicenseQualificationEvidence,
    ParserQualificationEvidence,
    PilotQualificationEvidence,
    ProductionQualificationReport,
    ScaleQualificationEvidence,
    SupplyChainQualificationEvidence,
)

T = TypeVar("T", bound=BaseModel)


class ProductionQualificationStore:
    def __init__(self, workspace: Path) -> None:
        self.root = workspace / "production-qualification"
        if self.root.is_symlink():
            raise ValueError("production qualification root cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        self.datasets = self._namespace("datasets")
        self.parsers = self._namespace("parsers")
        self.scale = self._namespace("scale")
        self.supply_chain = self._namespace("supply-chain")
        self.licenses = self._namespace("licenses")
        self.pilots = self._namespace("pilots")
        self.reports = self._namespace("reports")
        self.locks = self._namespace("locks")

    def commit_dataset(self, value: DatasetQualificationEvidence) -> DatasetQualificationEvidence:
        return self._commit(self.datasets, value.evidence_id, value, DatasetQualificationEvidence)

    def read_dataset(self, evidence_id: str) -> DatasetQualificationEvidence:
        return self._read(self.datasets, evidence_id, DatasetQualificationEvidence)

    def list_datasets(self) -> list[DatasetQualificationEvidence]:
        return self._list(self.datasets, DatasetQualificationEvidence)

    def commit_parser(self, value: ParserQualificationEvidence) -> ParserQualificationEvidence:
        return self._commit(self.parsers, value.evidence_id, value, ParserQualificationEvidence)

    def read_parser(self, evidence_id: str) -> ParserQualificationEvidence:
        return self._read(self.parsers, evidence_id, ParserQualificationEvidence)

    def list_parsers(self) -> list[ParserQualificationEvidence]:
        return self._list(self.parsers, ParserQualificationEvidence)

    def commit_scale(self, value: ScaleQualificationEvidence) -> ScaleQualificationEvidence:
        return self._commit(self.scale, value.evidence_id, value, ScaleQualificationEvidence)

    def read_scale(self, evidence_id: str) -> ScaleQualificationEvidence:
        return self._read(self.scale, evidence_id, ScaleQualificationEvidence)

    def list_scale(self) -> list[ScaleQualificationEvidence]:
        return self._list(self.scale, ScaleQualificationEvidence)

    def commit_supply_chain(
        self, value: SupplyChainQualificationEvidence
    ) -> SupplyChainQualificationEvidence:
        return self._commit(
            self.supply_chain, value.evidence_id, value, SupplyChainQualificationEvidence
        )

    def read_supply_chain(self, evidence_id: str) -> SupplyChainQualificationEvidence:
        return self._read(self.supply_chain, evidence_id, SupplyChainQualificationEvidence)

    def list_supply_chain(self) -> list[SupplyChainQualificationEvidence]:
        return self._list(self.supply_chain, SupplyChainQualificationEvidence)

    def commit_license(self, value: LicenseQualificationEvidence) -> LicenseQualificationEvidence:
        return self._commit(self.licenses, value.evidence_id, value, LicenseQualificationEvidence)

    def read_license(self, evidence_id: str) -> LicenseQualificationEvidence:
        return self._read(self.licenses, evidence_id, LicenseQualificationEvidence)

    def list_licenses(self) -> list[LicenseQualificationEvidence]:
        return self._list(self.licenses, LicenseQualificationEvidence)

    def commit_pilot(self, value: PilotQualificationEvidence) -> PilotQualificationEvidence:
        return self._commit(self.pilots, value.evidence_id, value, PilotQualificationEvidence)

    def read_pilot(self, evidence_id: str) -> PilotQualificationEvidence:
        return self._read(self.pilots, evidence_id, PilotQualificationEvidence)

    def list_pilots(self) -> list[PilotQualificationEvidence]:
        return self._list(self.pilots, PilotQualificationEvidence)

    def commit_report(self, value: ProductionQualificationReport) -> ProductionQualificationReport:
        return self._commit(self.reports, value.report_id, value, ProductionQualificationReport)

    def read_report(self, report_id: str) -> ProductionQualificationReport:
        return self._read(self.reports, report_id, ProductionQualificationReport)

    def list_reports(self) -> list[ProductionQualificationReport]:
        return self._list(self.reports, ProductionQualificationReport)

    @contextmanager
    def control_lock(
        self, timeout_seconds: float = 30.0, stale_seconds: float = 600.0
    ) -> Iterator[None]:
        self._validate_namespace(self.locks)
        lock = self.locks / "production-qualification.lock"
        deadline = time.monotonic() + timeout_seconds
        token = uuid.uuid4().hex
        fd: int | None = None
        while fd is None:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, token.encode("ascii"))
                os.fsync(fd)
            except FileExistsError:
                try:
                    stale = time.time() - lock.stat().st_mtime > stale_seconds
                except FileNotFoundError:
                    continue
                if stale:
                    lock.unlink(missing_ok=True)
                    continue
                if time.monotonic() >= deadline:
                    raise ProductionStoreCorruptError(
                        "timed out acquiring production qualification lock"
                    )
                time.sleep(0.05)
        try:
            yield
        finally:
            if fd is not None:
                os.close(fd)
            lock.unlink(missing_ok=True)

    def _namespace(self, name: str) -> Path:
        path = self.root / name
        if path.is_symlink():
            raise ValueError("production qualification namespace cannot be a symlink")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _validate_namespace(self, path: Path) -> None:
        if path.is_symlink() or not path.is_dir():
            raise ProductionStoreCorruptError(
                "production qualification namespace is unsafe"
            )
        try:
            path.resolve(strict=True).relative_to(self.root.resolve(strict=True))
        except (FileNotFoundError, ValueError) as exc:
            raise ProductionStoreCorruptError(
                "production qualification namespace escaped its root"
            ) from exc

    def _commit(self, namespace: Path, record_id: str, value: T, model: type[T]) -> T:
        validate_safe_id(record_id)
        self._validate_namespace(namespace)
        destination = namespace / record_id
        with self.control_lock():
            if destination.exists():
                existing = self._read(namespace, record_id, model)
                existing_digest = getattr(existing, "semantic_digest")()
                value_digest = getattr(value, "semantic_digest")()
                if existing_digest != value_digest:
                    raise ProductionStoreCorruptError(
                        "immutable production qualification record conflicts with existing content"
                    )
                return existing
            raw = (value.model_dump_json(exclude_none=False) + "\n").encode("utf-8")
            manifest = {
                "model": model.__name__,
                "record_sha256": hashlib.sha256(raw).hexdigest(),
                "semantic_sha256": getattr(value, "semantic_digest")(),
            }
            temp = Path(tempfile.mkdtemp(prefix=f".{record_id}-", dir=namespace))
            try:
                self._safe_write(temp / "record.json", raw)
                self._safe_write(
                    temp / "manifest.json",
                    (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode(),
                )
                os.rename(temp, destination)
            finally:
                if temp.exists():
                    for child in temp.iterdir():
                        child.unlink(missing_ok=True)
                    temp.rmdir()
        return self._read(namespace, record_id, model)

    def _read(self, namespace: Path, record_id: str, model: type[T]) -> T:
        validate_safe_id(record_id)
        self._validate_namespace(namespace)
        directory = namespace / record_id
        if not directory.exists():
            raise FileNotFoundError(record_id)
        if directory.is_symlink() or not directory.is_dir():
            raise ProductionStoreCorruptError("production qualification record is unsafe")
        record_path = directory / "record.json"
        manifest_path = directory / "manifest.json"
        if any(path.is_symlink() or not path.is_file() for path in (record_path, manifest_path)):
            raise ProductionStoreCorruptError("production qualification record is incomplete")
        raw = record_path.read_bytes()
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProductionStoreCorruptError(
                "production qualification manifest is invalid JSON"
            ) from exc
        if set(manifest) != {"model", "record_sha256", "semantic_sha256"}:
            raise ProductionStoreCorruptError("production qualification manifest shape is invalid")
        if manifest["model"] != model.__name__:
            raise ProductionStoreCorruptError("production qualification model identity mismatch")
        if hashlib.sha256(raw).hexdigest() != manifest["record_sha256"]:
            raise ProductionStoreCorruptError("production qualification record checksum mismatch")
        value = model.model_validate_json(raw)
        if getattr(value, "semantic_digest")() != manifest["semantic_sha256"]:
            raise ProductionStoreCorruptError("production qualification semantic checksum mismatch")
        return value

    def _list(self, namespace: Path, model: type[T]) -> list[T]:
        self._validate_namespace(namespace)
        result: list[T] = []
        for path in sorted(namespace.iterdir()):
            if path.name.startswith("."):
                continue
            result.append(self._read(namespace, path.name, model))
        return result

    @staticmethod
    def _safe_write(path: Path, raw: bytes) -> None:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise ProductionStoreCorruptError(
                        "production qualification write did not make progress"
                    )
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
