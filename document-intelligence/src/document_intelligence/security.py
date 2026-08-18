from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_SAFE_TENANT = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
_SAFE_SUBJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,126}$")
_SAFE_RESOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SecurityConfigurationError(RuntimeError):
    pass


class AuthenticationError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    pass


class RateLimitError(RuntimeError):
    pass


class ConcurrencyLimitError(RuntimeError):
    pass


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    subject_id: str
    authenticated: bool


class EntitlementRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    tenant_id: str = Field(pattern=_SAFE_TENANT.pattern)
    resource_type: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,62}$")
    resource_id: str = Field(pattern=_SAFE_RESOURCE.pattern)
    granted_by_subject: str = Field(pattern=_SAFE_SUBJECT.pattern)
    granted_at: datetime
    record_sha256: str = Field(pattern=_SHA256.pattern)

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"record_sha256"})

    @classmethod
    def create(
        cls, *, principal: Principal, resource_type: str, resource_id: str
    ) -> "EntitlementRecord":
        payload = {
            "schema_version": 1,
            "tenant_id": principal.tenant_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "granted_by_subject": principal.subject_id,
            "granted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(**payload, record_sha256=digest)

    def verify(self) -> None:
        expected = hashlib.sha256(
            json.dumps(
                self.payload(), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        if not hmac.compare_digest(expected, self.record_sha256):
            raise AuthorizationError("entitlement record integrity check failed")


class AccessAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    event_id: str = Field(pattern=r"^access_[0-9a-f]{32}$")
    occurred_at: datetime
    request_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(pattern=_SAFE_TENANT.pattern)
    subject_id: str = Field(pattern=_SAFE_SUBJECT.pattern)
    method: str = Field(min_length=1, max_length=16)
    path_class: str = Field(min_length=1, max_length=255)
    status_code: int = Field(ge=100, le=599)
    duration_ms: float = Field(ge=0.0)
    outcome: str = Field(pattern=r"^(allowed|denied|limited|failed)$")
    event_sha256: str = Field(pattern=_SHA256.pattern)

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"event_sha256"})

    def verify(self) -> None:
        expected = hashlib.sha256(
            json.dumps(
                self.payload(), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        if not hmac.compare_digest(expected, self.event_sha256):
            raise AuthorizationError("access audit record integrity check failed")


class SecurityStore:
    """Single-node entitlement and access-audit store.

    Records are immutable and content verified. A resource can be entitled to more than one
    tenant without duplicating the underlying content-addressed artifact.
    """

    def __init__(self, workspace: Path) -> None:
        self.root = workspace / "security"
        self.entitlement_root = self.root / "entitlements"
        self.audit_root = self.root / "access-audit"
        self._lock = threading.RLock()

    @staticmethod
    def _safe(value: str, pattern: re.Pattern[str], label: str) -> str:
        if not pattern.fullmatch(value):
            raise AuthorizationError(f"invalid {label}")
        return value

    def _ensure_roots(self) -> None:
        for path in (self.root, self.entitlement_root, self.audit_root):
            if path.exists() and path.is_symlink():
                raise AuthorizationError("security namespace must not be a symlink")
            path.mkdir(parents=True, exist_ok=True)

    def grant(
        self, principal: Principal, resource_type: str, resource_id: str
    ) -> EntitlementRecord:
        if not principal.authenticated:
            return EntitlementRecord.create(
                principal=principal, resource_type=resource_type, resource_id=resource_id
            )
        tenant = self._safe(principal.tenant_id, _SAFE_TENANT, "tenant id")
        resource_type = self._safe(resource_type, _SAFE_TENANT, "resource type")
        resource_id = self._safe(resource_id, _SAFE_RESOURCE, "resource id")
        record = EntitlementRecord.create(
            principal=principal, resource_type=resource_type, resource_id=resource_id
        )
        with self._lock:
            self._ensure_roots()
            target_dir = self.entitlement_root / tenant / resource_type
            target_dir.mkdir(parents=True, exist_ok=True)
            if target_dir.is_symlink():
                raise AuthorizationError("entitlement namespace must not be a symlink")
            target = target_dir / f"{resource_id}.json"
            if target.exists():
                existing = self.read_entitlement(tenant, resource_type, resource_id)
                return existing
            tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            encoded = json.dumps(
                record.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            )
            with tmp.open("x", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
            return record

    def read_entitlement(
        self, tenant_id: str, resource_type: str, resource_id: str
    ) -> EntitlementRecord:
        tenant_id = self._safe(tenant_id, _SAFE_TENANT, "tenant id")
        resource_type = self._safe(resource_type, _SAFE_TENANT, "resource type")
        resource_id = self._safe(resource_id, _SAFE_RESOURCE, "resource id")
        self._ensure_roots()
        target = self.entitlement_root / tenant_id / resource_type / f"{resource_id}.json"
        if not target.is_file() or target.is_symlink():
            raise AuthorizationError("resource is not available to this tenant")
        try:
            record = EntitlementRecord.model_validate_json(target.read_text(encoding="utf-8"))
        except Exception as exc:
            raise AuthorizationError("entitlement record is invalid") from exc
        record.verify()
        if (
            record.tenant_id != tenant_id
            or record.resource_type != resource_type
            or record.resource_id != resource_id
        ):
            raise AuthorizationError("entitlement record identity mismatch")
        return record

    def require(self, principal: Principal, resource_type: str, resource_id: str) -> None:
        if principal.authenticated:
            self.read_entitlement(principal.tenant_id, resource_type, resource_id)

    def audit(
        self,
        *,
        principal: Principal,
        request_id: str,
        method: str,
        path_class: str,
        status_code: int,
        duration_ms: float,
        outcome: str,
    ) -> AccessAuditEvent:
        occurred_at = datetime.now(timezone.utc)
        event_id = f"access_{uuid.uuid4().hex}"
        payload = {
            "schema_version": 1,
            "event_id": event_id,
            "occurred_at": occurred_at.isoformat().replace("+00:00", "Z"),
            "request_id": request_id,
            "tenant_id": principal.tenant_id,
            "subject_id": principal.subject_id,
            "method": method,
            "path_class": path_class,
            "status_code": status_code,
            "duration_ms": round(max(0.0, duration_ms), 3),
            "outcome": outcome,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        event = AccessAuditEvent(**payload, event_sha256=digest)
        if not principal.authenticated:
            return event
        with self._lock:
            self._ensure_roots()
            day = occurred_at.strftime("%Y-%m-%d")
            directory = self.audit_root / day
            directory.mkdir(parents=True, exist_ok=True)
            if directory.is_symlink():
                raise AuthorizationError("audit namespace must not be a symlink")
            target = directory / f"{event_id}.json"
            encoded = json.dumps(
                event.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            )
            with target.open("x", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        return event

    def read_audit_event(self, day: str, event_id: str) -> AccessAuditEvent:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise AuthorizationError("invalid audit day")
        if not re.fullmatch(r"access_[0-9a-f]{32}", event_id):
            raise AuthorizationError("invalid audit event id")
        self._ensure_roots()
        target = self.audit_root / day / f"{event_id}.json"
        if not target.is_file() or target.is_symlink():
            raise AuthorizationError("access audit event not found")
        try:
            event = AccessAuditEvent.model_validate_json(
                target.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise AuthorizationError("access audit record is invalid") from exc
        event.verify()
        if event.event_id != event_id:
            raise AuthorizationError("access audit identity mismatch")
        return event


class SecurityManager:
    def __init__(
        self,
        *,
        workspace: Path,
        production: bool,
        tenant_token_sha256: dict[str, str],
        requests_per_minute: int,
        max_concurrent_per_tenant: int,
    ) -> None:
        self.production = production
        self._tokens = dict(tenant_token_sha256)
        self.store = SecurityStore(workspace)
        self._rpm = requests_per_minute
        self._max_concurrent = max_concurrent_per_tenant
        self._lock = threading.RLock()
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._active: dict[str, int] = defaultdict(int)
        if production:
            if not self._tokens:
                raise SecurityConfigurationError("production requires tenant API tokens")
            for tenant, digest in self._tokens.items():
                if not _SAFE_TENANT.fullmatch(tenant) or not _SHA256.fullmatch(digest):
                    raise SecurityConfigurationError(
                        "invalid production tenant token configuration"
                    )

    def authenticate(
        self, *, token: str | None, tenant_id: str | None, subject_id: str | None
    ) -> Principal:
        if not self.production:
            tenant = (
                tenant_id
                if tenant_id and _SAFE_TENANT.fullmatch(tenant_id)
                else "development"
            )
            subject = (
                subject_id
                if subject_id and _SAFE_SUBJECT.fullmatch(subject_id)
                else "local-user"
            )
            return Principal(tenant, subject, False)
        if token is None or tenant_id is None or subject_id is None:
            raise AuthenticationError("API token, tenant id and subject id are required")
        if not _SAFE_TENANT.fullmatch(tenant_id) or not _SAFE_SUBJECT.fullmatch(subject_id):
            raise AuthenticationError("invalid tenant or subject identity")
        expected = self._tokens.get(tenant_id)
        if expected is None:
            raise AuthenticationError("invalid API credentials")
        actual = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(actual, expected):
            raise AuthenticationError("invalid API credentials")
        return Principal(tenant_id, subject_id, True)

    def enter_request(self, principal: Principal) -> None:
        if not self.production:
            return
        now = time.monotonic()
        with self._lock:
            window = self._windows[principal.tenant_id]
            cutoff = now - 60.0
            while window and window[0] < cutoff:
                window.popleft()
            if len(window) >= self._rpm:
                raise RateLimitError("tenant request rate exceeded")
            if self._active[principal.tenant_id] >= self._max_concurrent:
                raise ConcurrencyLimitError("tenant concurrent request limit exceeded")
            window.append(now)
            self._active[principal.tenant_id] += 1

    def exit_request(self, principal: Principal) -> None:
        if not self.production:
            return
        with self._lock:
            current = self._active.get(principal.tenant_id, 0)
            self._active[principal.tenant_id] = max(0, current - 1)

    @staticmethod
    def request_id(value: str | None) -> str:
        if value and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
            return value
        return f"req_{uuid.uuid4().hex}"

    @staticmethod
    def path_class(path: str) -> str:
        parts = [part for part in path.split("/") if part]
        safe: list[str] = []
        for part in parts[:5]:
            if len(part) > 48 or re.fullmatch(r"[a-z]+_[0-9a-f]{12,}", part):
                safe.append("{id}")
            else:
                safe.append(part)
        return "/" + "/".join(safe)
