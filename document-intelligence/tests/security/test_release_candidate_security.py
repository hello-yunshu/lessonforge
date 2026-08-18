from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from document_intelligence.api.main import create_app
from document_intelligence.config import Settings
from document_intelligence.observability import MetricsRegistry
from document_intelligence.security import (
    AuthorizationError,
    Principal,
    SecurityManager,
    SecurityStore,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def production_settings(tmp_path: Path, **updates: object) -> Settings:
    values: dict[str, object] = {
        "deployment_profile": "production",
        "workspace": (tmp_path / "workspace").resolve(),
        "api_tenant_tokens_sha256": {
            "tenant-a": digest("token-a"),
            "tenant-b": digest("token-b"),
        },
        "pdf_render_backend": "disabled",
        "parser_config": Path(__file__).resolve().parents[2] / "configs" / "parsers.yaml",
    }
    values.update(updates)
    return Settings(**values)


def headers(tenant: str, token: str, subject: str = "tester") -> dict[str, str]:
    return {
        "X-Tenant-ID": tenant,
        "X-API-Token": token,
        "X-Subject-ID": subject,
    }


def test_production_settings_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="DI_API_TENANT_TOKENS_SHA256_JSON"):
        Settings(
            deployment_profile="production",
            workspace=(tmp_path / "workspace").resolve(),
            pdf_render_backend="disabled",
        )
    with pytest.raises(ValidationError, match="resolved license"):
        production_settings(tmp_path, pdf_render_backend="pymupdf")
    with pytest.raises(ValidationError, match="token digests"):
        production_settings(tmp_path, enable_standard_writes=True)


def test_production_api_requires_auth_and_hides_docs(tmp_path: Path) -> None:
    app = create_app(production_settings(tmp_path))
    with TestClient(app) as client:
        assert client.get("/v1/parsers").status_code == 401
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/livez").status_code == 200
        assert client.get("/metrics").status_code == 404
        response = client.get("/v1/parsers", headers=headers("tenant-a", "token-a"))
        assert response.status_code == 200
        assert response.headers["X-Request-ID"].startswith("req_")


def test_run_entitlement_is_tenant_scoped(
    tmp_path: Path, fixtures_dir: Path
) -> None:
    app = create_app(production_settings(tmp_path))
    source = fixtures_dir / "native_text.pdf"
    with TestClient(app) as client:
        created = client.post(
            "/v1/parse",
            headers=headers("tenant-a", "token-a"),
            files={"file": (source.name, source.read_bytes(), "application/pdf")},
            data={"parser_id": "native-pdf"},
        )
        assert created.status_code == 200, created.text
        run_id = created.json()["run"]["parse_run_id"]
        assert (
            client.get(
                f"/v1/runs/{run_id}", headers=headers("tenant-a", "token-a")
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/v1/runs/{run_id}", headers=headers("tenant-b", "token-b")
            ).status_code
            == 404
        )
    audit_root = tmp_path / "workspace" / "security" / "access-audit"
    audit_files = list(audit_root.rglob("*.json"))
    assert audit_files
    events = [
        app.state.security.store.read_audit_event(path.parent.name, path.stem)
        for path in audit_files
    ]
    assert any(event.tenant_id == "tenant-a" for event in events)


def test_rate_limit_is_enforced_per_tenant(tmp_path: Path) -> None:
    app = create_app(production_settings(tmp_path, api_requests_per_minute=1))
    with TestClient(app) as client:
        first = client.get("/v1/parsers", headers=headers("tenant-a", "token-a"))
        second = client.get("/v1/parsers", headers=headers("tenant-a", "token-a"))
        other = client.get("/v1/parsers", headers=headers("tenant-b", "token-b"))
        assert first.status_code == 200
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "RATE_LIMITED"
        assert other.status_code == 200


def test_entitlement_tamper_is_detected(tmp_path: Path) -> None:
    store = SecurityStore(tmp_path / "workspace")
    principal = Principal("tenant-a", "reviewer", True)
    store.grant(principal, "run", "run_123")
    path = (
        tmp_path
        / "workspace"
        / "security"
        / "entitlements"
        / "tenant-a"
        / "run"
        / "run_123.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["resource_id"] = "run_456"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AuthorizationError, match="integrity"):
        store.read_entitlement("tenant-a", "run", "run_123")


def test_security_manager_rejects_bad_credentials(tmp_path: Path) -> None:
    manager = SecurityManager(
        workspace=tmp_path / "workspace",
        production=True,
        tenant_token_sha256={"tenant-a": digest("token-a")},
        requests_per_minute=5,
        max_concurrent_per_tenant=1,
    )
    with pytest.raises(Exception, match="invalid API credentials"):
        manager.authenticate(token="wrong", tenant_id="tenant-a", subject_id="user")


def test_metrics_are_prometheus_compatible() -> None:
    metrics = MetricsRegistry()
    metrics.request_started()
    metrics.request_finished("GET", "/v1/runs/{id}", 200, 0.125)
    rendered = metrics.render_prometheus()
    assert "document_intelligence_http_requests_total" in rendered
    assert 'path="/v1/runs/{id}"' in rendered
    assert "document_intelligence_http_inflight_requests 0" in rendered
