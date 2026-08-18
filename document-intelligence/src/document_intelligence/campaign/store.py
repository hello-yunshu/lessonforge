from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import uuid
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from document_intelligence.exceptions import QualificationCampaignStoreCorruptError
from document_intelligence.schema import validate_safe_id

from .models import CampaignBundleManifest, CampaignEvent, CampaignManifest


class CampaignStore:
    def __init__(self, workspace: Path, *, max_bundle_bytes: int = 32 * 1024 * 1024) -> None:
        self.root = workspace / "qualification-campaigns"
        if self.root.is_symlink():
            raise ValueError("campaign root cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        self.campaigns = self._namespace("campaigns")
        self.exports = self._namespace("exports")
        self.locks = self._namespace("locks")
        self.max_bundle_bytes = max_bundle_bytes

    def commit_manifest(self, value: CampaignManifest) -> CampaignManifest:
        validate_safe_id(value.campaign_id)
        destination = self.campaigns / value.campaign_id
        with self.control_lock(value.campaign_id):
            if destination.exists():
                existing = self.read_manifest(value.campaign_id)
                if existing.semantic_digest() != value.semantic_digest():
                    raise QualificationCampaignStoreCorruptError(
                        "immutable campaign manifest conflicts with existing content"
                    )
                return existing
            temp = Path(tempfile.mkdtemp(prefix=f".{value.campaign_id}-", dir=self.campaigns))
            try:
                raw = (value.model_dump_json(exclude_none=False) + "\n").encode()
                self._safe_write(temp / "manifest.json", raw)
                self._safe_write(
                    temp / "manifest.sha256",
                    (hashlib.sha256(raw).hexdigest() + "\n").encode(),
                )
                (temp / "events").mkdir(mode=0o700)
                os.rename(temp, destination)
            finally:
                self._cleanup_temp(temp)
        return self.read_manifest(value.campaign_id)

    def read_manifest(self, campaign_id: str) -> CampaignManifest:
        directory = self._campaign_dir(campaign_id)
        raw = self._verified_file(directory / "manifest.json", directory / "manifest.sha256")
        return CampaignManifest.model_validate_json(raw)

    def append_event(self, campaign_id: str, event: CampaignEvent) -> CampaignEvent:
        validate_safe_id(campaign_id)
        if event.campaign_id != campaign_id:
            raise QualificationCampaignStoreCorruptError("campaign event identity mismatch")
        with self.control_lock(campaign_id):
            events = self.read_events(campaign_id)
            expected_sequence = len(events) + 1
            previous = events[-1].chain_digest() if events else None
            if event.sequence != expected_sequence or event.previous_event_sha256 != previous:
                raise QualificationCampaignStoreCorruptError("campaign event chain is inconsistent")
            events_dir = self._events_dir(campaign_id)
            destination = events_dir / f"{event.sequence:08d}-{event.event_id}"
            if destination.exists():
                existing = self._read_event_dir(destination)
                if existing.model_dump(mode="json") != event.model_dump(mode="json"):
                    raise QualificationCampaignStoreCorruptError(
                        "immutable campaign event conflicts with existing content"
                    )
                return existing
            raw = (event.model_dump_json(exclude_none=False) + "\n").encode()
            temp = Path(tempfile.mkdtemp(prefix=f".{event.event_id}-", dir=events_dir))
            try:
                self._safe_write(temp / "event.json", raw)
                self._safe_write(
                    temp / "event.sha256", (hashlib.sha256(raw).hexdigest() + "\n").encode()
                )
                os.rename(temp, destination)
            finally:
                self._cleanup_temp(temp)
        return self._read_event_dir(destination)

    def read_events(self, campaign_id: str) -> list[CampaignEvent]:
        events_dir = self._events_dir(campaign_id)
        result: list[CampaignEvent] = []
        previous: str | None = None
        for path in sorted(events_dir.iterdir()):
            if path.name.startswith("."):
                continue
            event = self._read_event_dir(path)
            if event.sequence != len(result) + 1 or event.previous_event_sha256 != previous:
                raise QualificationCampaignStoreCorruptError("campaign event chain is broken")
            previous = event.chain_digest()
            result.append(event)
        return result

    def list_campaign_ids(self) -> list[str]:
        self._validate_namespace(self.campaigns)
        return sorted(
            path.name
            for path in self.campaigns.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        )

    def export_bundle(
        self,
        campaign_id: str,
        *,
        evidence_files: dict[str, bytes],
        output: Path,
    ) -> CampaignBundleManifest:
        if output.exists():
            raise FileExistsError(output)
        manifest = self.read_manifest(campaign_id)
        events = self.read_events(campaign_id)
        files: dict[str, bytes] = {
            "campaign/manifest.json": (
                manifest.model_dump_json(exclude_none=False) + "\n"
            ).encode(),
            "campaign/events.json": (
                json.dumps(
                    [event.model_dump(mode="json") for event in events],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode(),
        }
        files.update(evidence_files)
        total = sum(len(raw) for raw in files.values())
        if total > self.max_bundle_bytes or len(files) > 512:
            raise QualificationCampaignStoreCorruptError(
                "campaign bundle exceeds configured limits"
            )
        file_digests = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
        event_chain = events[-1].chain_digest() if events else None
        bundle_id = "bundle-" + hashlib.sha256(
            json.dumps(file_digests, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:32]
        bundle_manifest = CampaignBundleManifest(
            bundle_id=bundle_id,
            campaign_id=campaign_id,
            campaign_manifest_sha256=hashlib.sha256(files["campaign/manifest.json"]).hexdigest(),
            event_chain_sha256=event_chain,
            files=file_digests,
            created_at=events[-1].created_at if events else manifest.created_at,
        )
        files["bundle-manifest.json"] = (
            bundle_manifest.model_dump_json(exclude_none=False) + "\n"
        ).encode()
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{bundle_id}-", suffix=".zip", dir=output.parent)
        os.close(fd)
        temp = Path(temp_name)
        try:
            with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, raw in sorted(files.items()):
                    info = zipfile.ZipInfo(name)
                    info.date_time = (1980, 1, 1, 0, 0, 0)
                    info.external_attr = 0o600 << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, raw)
            if temp.stat().st_size > self.max_bundle_bytes:
                raise QualificationCampaignStoreCorruptError("campaign bundle archive is too large")
            os.replace(temp, output)
        finally:
            temp.unlink(missing_ok=True)
        return self.verify_bundle(output)[0]

    def verify_bundle(self, path: Path) -> tuple[CampaignBundleManifest, dict[str, bytes]]:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > self.max_bundle_bytes:
            raise QualificationCampaignStoreCorruptError("campaign bundle file is unsafe")
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > 513:
                raise QualificationCampaignStoreCorruptError("campaign bundle file count invalid")
            names: set[str] = set()
            payload: dict[str, bytes] = {}
            total = 0
            declared_total = sum(info.file_size for info in infos)
            if declared_total > self.max_bundle_bytes:
                raise QualificationCampaignStoreCorruptError(
                    "campaign bundle declared size exceeds limit"
                )
            for info in infos:
                pure = PurePosixPath(info.filename)
                if info.file_size > self.max_bundle_bytes:
                    raise QualificationCampaignStoreCorruptError(
                        "campaign bundle member exceeds limit"
                    )
                if info.file_size and info.compress_size == 0:
                    raise QualificationCampaignStoreCorruptError(
                        "campaign bundle member has invalid compressed size"
                    )
                if info.compress_size and info.file_size / info.compress_size > 200:
                    raise QualificationCampaignStoreCorruptError(
                        "campaign bundle compression ratio is unsafe"
                    )
                if (
                    info.filename in names
                    or pure.is_absolute()
                    or ".." in pure.parts
                    or "\\" in info.filename
                    or info.is_dir()
                ):
                    raise QualificationCampaignStoreCorruptError("campaign bundle path is unsafe")
                names.add(info.filename)
                raw = archive.read(info)
                total += len(raw)
                if total > self.max_bundle_bytes:
                    raise QualificationCampaignStoreCorruptError(
                        "campaign bundle expands too large"
                    )
                payload[info.filename] = raw
        raw_manifest = payload.pop("bundle-manifest.json", None)
        if raw_manifest is None:
            raise QualificationCampaignStoreCorruptError("campaign bundle manifest is missing")
        bundle = CampaignBundleManifest.model_validate_json(raw_manifest)
        if set(payload) != set(bundle.files):
            raise QualificationCampaignStoreCorruptError("campaign bundle file set mismatch")
        for name, digest in bundle.files.items():
            if hashlib.sha256(payload[name]).hexdigest() != digest:
                raise QualificationCampaignStoreCorruptError("campaign bundle checksum mismatch")
        if (
            hashlib.sha256(payload["campaign/manifest.json"]).hexdigest()
            != bundle.campaign_manifest_sha256
        ):
            raise QualificationCampaignStoreCorruptError(
                "campaign bundle manifest digest mismatch"
            )
        manifest = CampaignManifest.model_validate_json(payload["campaign/manifest.json"])
        if manifest.campaign_id != bundle.campaign_id:
            raise QualificationCampaignStoreCorruptError("campaign bundle identity mismatch")
        events_raw = json.loads(payload["campaign/events.json"])
        events = [CampaignEvent.model_validate(item) for item in events_raw]
        previous: str | None = None
        for index, event in enumerate(events, start=1):
            if event.sequence != index or event.previous_event_sha256 != previous:
                raise QualificationCampaignStoreCorruptError("campaign bundle event chain broken")
            previous = event.chain_digest()
        if previous != bundle.event_chain_sha256:
            raise QualificationCampaignStoreCorruptError("campaign bundle chain digest mismatch")
        return bundle, payload

    @contextmanager
    def control_lock(self, campaign_id: str, timeout_seconds: float = 30.0) -> Iterator[None]:
        validate_safe_id(campaign_id)
        self._validate_namespace(self.locks)
        lock = self.locks / f"{campaign_id}.lock"
        deadline = time.monotonic() + timeout_seconds
        token = uuid.uuid4().hex.encode()
        fd: int | None = None
        while fd is None:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(fd, token)
                os.fsync(fd)
            except FileExistsError:
                try:
                    stale = time.time() - lock.stat().st_mtime > 600
                except FileNotFoundError:
                    continue
                if stale:
                    lock.unlink(missing_ok=True)
                    continue
                if time.monotonic() >= deadline:
                    raise QualificationCampaignStoreCorruptError("campaign lock timed out")
                time.sleep(0.05)
        try:
            yield
        finally:
            if fd is not None:
                os.close(fd)
            lock.unlink(missing_ok=True)

    def _campaign_dir(self, campaign_id: str) -> Path:
        validate_safe_id(campaign_id)
        self._validate_namespace(self.campaigns)
        directory = self.campaigns / campaign_id
        if not directory.is_dir() or directory.is_symlink():
            raise FileNotFoundError(campaign_id)
        return directory

    def _events_dir(self, campaign_id: str) -> Path:
        path = self._campaign_dir(campaign_id) / "events"
        self._validate_under_root(path)
        if not path.is_dir() or path.is_symlink():
            raise QualificationCampaignStoreCorruptError("campaign events namespace is unsafe")
        return path

    def _read_event_dir(self, directory: Path) -> CampaignEvent:
        self._validate_under_root(directory)
        if directory.is_symlink() or not directory.is_dir():
            raise QualificationCampaignStoreCorruptError("campaign event directory is unsafe")
        raw = self._verified_file(directory / "event.json", directory / "event.sha256")
        return CampaignEvent.model_validate_json(raw)

    def _verified_file(self, path: Path, digest_path: Path) -> bytes:
        if any(item.is_symlink() or not item.is_file() for item in (path, digest_path)):
            raise QualificationCampaignStoreCorruptError("campaign record is incomplete")
        raw = path.read_bytes()
        expected = digest_path.read_text(encoding="ascii").strip()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise QualificationCampaignStoreCorruptError("campaign record checksum mismatch")
        return raw

    def _namespace(self, name: str) -> Path:
        path = self.root / name
        if path.is_symlink():
            raise ValueError("campaign namespace cannot be a symlink")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _validate_namespace(self, path: Path) -> None:
        if path.is_symlink() or not path.is_dir():
            raise QualificationCampaignStoreCorruptError("campaign namespace is unsafe")
        self._validate_under_root(path)

    def _validate_under_root(self, path: Path) -> None:
        try:
            path.resolve(strict=True).relative_to(self.root.resolve(strict=True))
        except (FileNotFoundError, ValueError) as exc:
            raise QualificationCampaignStoreCorruptError("campaign path escaped root") from exc

    @staticmethod
    def _safe_write(path: Path, raw: bytes) -> None:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise QualificationCampaignStoreCorruptError("campaign write stalled")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _cleanup_temp(path: Path) -> None:
        if not path.exists():
            return
        for child in path.rglob("*"):
            if child.is_file():
                child.unlink(missing_ok=True)
        directories = sorted(
            (item for item in path.rglob("*") if item.is_dir()),
            key=lambda item: len(item.parts),
            reverse=True,
        )
        for child in directories:
            child.rmdir()
        path.rmdir()
