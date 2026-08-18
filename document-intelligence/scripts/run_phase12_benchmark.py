from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError

from document_intelligence.api.main import create_app
from document_intelligence.config import Settings

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "docs" / "phase-12" / "benchmark_results.json"
OUT_MD = ROOT / "docs" / "phase-12" / "RELEASE_CANDIDATE_BENCHMARK.md"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def headers(tenant: str, token: str) -> dict[str, str]:
    return {
        "X-Tenant-ID": tenant,
        "X-API-Token": token,
        "X-Subject-ID": "phase12-benchmark",
    }


def main() -> None:
    checks: list[dict[str, object]] = []
    parser_config = ROOT / "configs" / "parsers.yaml"
    fixture = ROOT / "tests" / "fixtures" / "native_text.pdf"
    with tempfile.TemporaryDirectory(prefix="di-phase12-") as temp_value:
        workspace = (Path(temp_value) / "workspace").resolve()
        try:
            Settings(
                deployment_profile="production",
                workspace=workspace,
                parser_config=parser_config,
                pdf_render_backend="disabled",
            )
        except ValidationError:
            fail_closed = True
        else:
            fail_closed = False
        checks.append({"name": "production-config-fails-closed", "passed": fail_closed})
        settings = Settings(
            deployment_profile="production",
            workspace=workspace,
            parser_config=parser_config,
            api_tenant_tokens_sha256={
                "tenant-a": digest("token-a"),
                "tenant-b": digest("token-b"),
            },
            pdf_render_backend="disabled",
            api_requests_per_minute=20,
        )
        with TestClient(create_app(settings)) as client:
            checks.append(
                {
                    "name": "core-api-auth-required",
                    "passed": client.get("/v1/parsers").status_code == 401,
                }
            )
            checks.append(
                {
                    "name": "production-docs-disabled",
                    "passed": client.get("/docs").status_code == 404,
                }
            )
            source = fixture.read_bytes()
            created = client.post(
                "/v1/parse",
                headers=headers("tenant-a", "token-a"),
                files={"file": (fixture.name, source, "application/pdf")},
                data={"parser_id": "native-pdf"},
            )
            run_id = created.json()["run"]["parse_run_id"]
            own = client.get(
                f"/v1/runs/{run_id}", headers=headers("tenant-a", "token-a")
            )
            foreign = client.get(
                f"/v1/runs/{run_id}", headers=headers("tenant-b", "token-b")
            )
            checks.append(
                {
                    "name": "tenant-resource-isolation",
                    "passed": own.status_code == 200 and foreign.status_code == 404,
                }
            )
            capabilities = client.get(
                "/v1/capabilities", headers=headers("tenant-a", "token-a")
            ).json()
            checks.append(
                {
                    "name": "capability-claims-are-bounded",
                    "passed": (
                        capabilities["release_status"] == "release-candidate"
                        and capabilities["capabilities"]["bounded_auto"]["enabled"]
                        is False
                        and capabilities["capabilities"]["standard_visual_matching"][
                            "status"
                        ]
                        == "disabled"
                    ),
                }
            )
            checks.append(
                {
                    "name": "access-audit-created",
                    "passed": bool(
                        list((workspace / "security" / "access-audit").rglob("*.json"))
                    ),
                }
            )
    license_ok = (ROOT / "LICENSE").is_file() and (ROOT / "NOTICE").is_file()
    checks.append({"name": "license-and-notice-present", "passed": license_ok})
    dockerfile = (ROOT / "deployments" / "docker" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    compose = (ROOT / "deployments" / "compose" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    checks.append(
        {
            "name": "container-defaults-fail-closed",
            "passed": (
                "ARG PYTHON_BASE_IMAGE" in dockerfile
                and "127.0.0.1:" in compose
                and "DI_DEPLOYMENT_PROFILE: production" in compose
            ),
        }
    )
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    checks.append(
        {
            "name": "single-current-ci-entrypoint",
            "passed": (
                "scripts/verify_all.py" in ci
                and "scripts/build_release_candidate.py" in ci
                and "pip-audit" in ci
            ),
        }
    )
    checks.append(
        {
            "name": "native-pdf-base-uses-pypdf",
            "passed": (
                "from pypdf import PdfReader"
                in (ROOT / "src/document_intelligence/parsers/native_pdf.py").read_text(
                    encoding="utf-8"
                )
            ),
        }
    )
    checks.append(
        {
            "name": "runtime-asserts-removed",
            "passed": not any(
                "assert " in path.read_text(encoding="utf-8")
                for path in (ROOT / "src" / "document_intelligence").rglob("*.py")
            ),
        }
    )
    payload = {
        "phase": 12,
        "version": "1.0.3-rc.1",
        "passed": all(bool(item["passed"]) for item in checks),
        "checks": checks,
        "production_qualified": False,
        "release_boundary": "single-node-self-hosted-release-candidate",
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Phase 12 Release Candidate Benchmark",
        "",
        f"- 通过：**{sum(bool(item['passed']) for item in checks)}/{len(checks)}**",
        "- 生产资格：**未取得**",
        "- 发布边界：受限单节点自托管候选版",
        "",
        "| 检查 | 结果 |",
        "|---|---|",
    ]
    lines.extend(
        f"| {item['name']} | {'通过' if item['passed'] else '失败'} |"
        for item in checks
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
