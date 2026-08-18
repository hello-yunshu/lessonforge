from __future__ import annotations

from fastapi.testclient import TestClient

from document_intelligence.api.main import create_app
from document_intelligence.freeze.registry import FROZEN_API_OPERATIONS


def test_freeze_endpoint_reports_exact_contract_match(settings) -> None:
    client = TestClient(create_app(settings))
    response = client.get("/v1/contracts/freeze")
    assert response.status_code == 200
    payload = response.json()
    assert payload["manifest"]["project_version"] == "1.0.0"
    assert payload["manifest"]["status"] == "engineering_frozen"
    assert payload["manifest"]["production_qualified"] is False
    assert payload["verification"]["compatible"] is True
    assert payload["verification"]["bounded_auto"] is False


def test_actual_api_surface_matches_frozen_registry(settings) -> None:
    app = create_app(settings)
    actual = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if route.path == "/healthz" or route.path.startswith("/v1/")
    }
    assert set(FROZEN_API_OPERATIONS).issubset(actual)
