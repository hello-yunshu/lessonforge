from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Sequence

from document_intelligence.exceptions import RillStoreCorruptError
from document_intelligence.rill.models import (
    DriftAlert,
    DriftState,
    ShadowFeedbackRecord,
    stable_rill_id,
)


class ShadowDriftMonitor:
    """Bounded, auditable host-side Shadow safety monitor.

    It is intentionally not a substitute for the RillML drift detectors.  It
    remains available when the external runtime is missing and can be rebuilt
    deterministically from immutable human feedback after the latest reset.
    """

    def __init__(
        self,
        workspace: Path,
        *,
        min_samples: int = 20,
        threshold: float = 5.0,
        delta: float = 0.01,
        recent_window: int = 100,
    ) -> None:
        self.root = workspace / "rill-shadow" / "drift"
        if self.root.is_symlink():
            raise ValueError("Rill drift namespace cannot be a symlink")
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "state.json"
        self.alerts_dir = self.root / "alerts"
        if self.alerts_dir.is_symlink():
            raise ValueError("Rill drift alert namespace cannot be a symlink")
        self.alerts_dir.mkdir(parents=True, exist_ok=True)
        self.lock_dir = self.root / ".lock"
        self.min_samples = min_samples
        self.threshold = threshold
        self.delta = delta
        self.recent_window = recent_window

    def read(self) -> DriftState:
        if not self.state_path.exists():
            return DriftState()
        if self.state_path.is_symlink():
            raise RillStoreCorruptError("Rill drift state cannot be a symlink")
        try:
            envelope = json.loads(self.state_path.read_text(encoding="utf-8"))
            if envelope.get("version") != 1 or not isinstance(envelope.get("state"), dict):
                raise ValueError("invalid drift state envelope")
            state_payload = envelope["state"]
            if self._digest(state_payload) != envelope.get("state_sha256"):
                raise ValueError("drift state digest mismatch")
            return DriftState.model_validate(state_payload)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise RillStoreCorruptError(
                "stored Rill drift state failed integrity verification"
            ) from exc

    def update(self, *, error: bool) -> tuple[DriftState, DriftAlert | None]:
        with self._lock():
            state, alert = self._advance(self.read(), error=error)
            self.write(state)
            return state, alert

    def reconcile(
        self,
        feedback: Sequence[ShadowFeedbackRecord],
        *,
        reset_after: datetime | None = None,
    ) -> DriftState:
        """Rebuild from immutable feedback so retries and process failures are idempotent."""
        ordered = sorted(feedback, key=lambda item: (item.created_at, item.feedback_id))
        if reset_after is not None:
            ordered = [item for item in ordered if item.created_at > reset_after]
        with self._lock():
            previous = self.read()
            state = DriftState(state_generation=previous.state_generation + 1)
            for record in ordered:
                state, _ = self._advance(state, error=not record.decision_correct)
            self.write(state)
            return state

    def _advance(self, state: DriftState, *, error: bool) -> tuple[DriftState, DriftAlert | None]:
        sample_count = state.sample_count + 1
        value = 1.0 if error else 0.0
        mean_error = state.mean_error + (value - state.mean_error) / sample_count
        cumulative = state.cumulative + value - mean_error - self.delta
        minimum = min(state.minimum_cumulative, cumulative)
        distance = max(0.0, cumulative - minimum)
        recent = [*state.recent_errors, int(error)][-self.recent_window :]
        alert = None
        alert_count = state.alert_count
        if sample_count >= self.min_samples and distance > self.threshold:
            recent_rate = sum(recent) / len(recent)
            alert_id = stable_rill_id(
                "drift-alert",
                str(sample_count),
                f"{recent_rate:.9f}",
                f"{mean_error:.9f}",
                f"{distance:.9f}",
                f"{self.threshold:.9f}",
            )
            alert = DriftAlert(
                alert_id=alert_id,
                sample_count=sample_count,
                recent_error_rate=recent_rate,
                baseline_error_rate=mean_error,
                page_hinkley_distance=distance,
                threshold=self.threshold,
                reason_codes=["SHADOW_ERROR_RATE_DRIFT"],
            )
            self._commit_alert(alert)
            alert_count += 1
            cumulative = 0.0
            minimum = 0.0
        return DriftState(
            sample_count=sample_count,
            mean_error=mean_error,
            cumulative=cumulative,
            minimum_cumulative=minimum,
            recent_errors=recent,
            alert_count=alert_count,
            state_generation=state.state_generation + 1,
        ), alert

    def reset(self) -> DriftState:
        with self._lock():
            previous = self.read()
            state = DriftState(state_generation=previous.state_generation + 1)
            self.write(state)
            return state

    def write(self, state: DriftState) -> None:
        state_payload = state.model_dump(mode="json")
        envelope = {
            "version": 1,
            "state": state_payload,
            "state_sha256": self._digest(state_payload),
        }
        payload = self._canonical(envelope) + b"\n"
        self._atomic_write(self.state_path, payload)

    def list_alerts(self) -> list[DriftAlert]:
        if self.root.is_symlink() or self.alerts_dir.is_symlink():
            raise RillStoreCorruptError("Rill drift namespace cannot be a symlink")
        results = []
        for path in sorted(self.alerts_dir.glob("*.json")):
            if path.is_symlink():
                raise RillStoreCorruptError("Rill drift alert cannot be a symlink")
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
                alert_payload = envelope["alert"]
                if envelope.get("version") != 1 or self._digest(alert_payload) != envelope.get(
                    "alert_sha256"
                ):
                    raise ValueError("invalid drift alert envelope")
                alert = DriftAlert.model_validate(alert_payload)
                if path.stem != alert.alert_id:
                    raise ValueError("drift alert identity mismatch")
                results.append(alert)
            except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
                raise RillStoreCorruptError(
                    "stored Rill drift alert failed integrity verification"
                ) from exc
        return results

    def checksum(self) -> str:
        return self._digest(self.read().model_dump(mode="json"))

    def _commit_alert(self, alert: DriftAlert) -> None:
        target = self.alerts_dir / f"{alert.alert_id}.json"
        if target.exists():
            # The alert ID is semantic; retain the first immutable timestamp only
            # when every other field is identical.
            existing = next(
                (item for item in self.list_alerts() if item.alert_id == alert.alert_id),
                None,
            )
            if existing is None:
                raise RillStoreCorruptError("existing drift alert cannot be verified")
            existing_payload = existing.model_dump(mode="json", exclude={"created_at"})
            candidate_payload = alert.model_dump(mode="json", exclude={"created_at"})
            if existing_payload != candidate_payload:
                raise RillStoreCorruptError(
                    "drift alert identifier contains different semantic content"
                )
            return
        alert_payload = alert.model_dump(mode="json")
        payload = self._canonical({
            "version": 1,
            "alert": alert_payload,
            "alert_sha256": self._digest(alert_payload),
        }) + b"\n"
        self._atomic_write(target, payload)

    @contextmanager
    def _lock(self, timeout_seconds: float = 5.0) -> Iterator[None]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                self.lock_dir.mkdir()
                (self.lock_dir / "owner.json").write_text(
                    json.dumps({"pid": os.getpid(), "created": time.time()}), encoding="utf-8"
                )
                break
            except FileExistsError:
                try:
                    age = time.time() - self.lock_dir.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age > 30:
                    shutil.rmtree(self.lock_dir, ignore_errors=True)
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError("timed out acquiring the Rill drift lock")
                time.sleep(0.02)
        try:
            yield
        finally:
            shutil.rmtree(self.lock_dir, ignore_errors=True)

    @staticmethod
    def _digest(payload: object) -> str:
        return hashlib.sha256(ShadowDriftMonitor._canonical(payload)).hexdigest()

    @staticmethod
    def _canonical(payload: object) -> bytes:
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
