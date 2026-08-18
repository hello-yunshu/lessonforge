from __future__ import annotations

import json
import tempfile
from pathlib import Path

from packaging.version import Version

from document_intelligence import __version__
from document_intelligence.api.main import create_app
from document_intelligence.config import Settings
from document_intelligence.domain_runtime import DomainPackRegistry, DomainRuntimeEngine
from document_intelligence.freeze import (
    FROZEN_API_OPERATIONS,
    FreezeBenchmarkCase,
    FreezeBenchmarkReport,
    FreezeService,
)
from document_intelligence.freeze.registry import AUDIT_RECORDS, PERMISSION_BOUNDARIES
from document_intelligence.rill.assist_models import BOUNDED_AUTO_ENABLED

ROOT = Path(__file__).resolve().parents[1]
JSON_OUT = ROOT / "docs/phase-9/benchmark_results.json"
MD_OUT = ROOT / "docs/phase-9/ONE_ZERO_FREEZE_BENCHMARK.md"


def case(name: str, passed: bool, **details: object) -> FreezeBenchmarkCase:
    return FreezeBenchmarkCase(name=name, passed=passed, details=details)


def main() -> None:
    service = FreezeService()
    manifest = service.load_manifest()
    verification = service.verify()
    settings = Settings()
    cases: list[FreezeBenchmarkCase] = [
        case(
            "contract-exact-match",
            verification.compatible and verification.exact_match,
            differences=len(verification.differences),
        ),
        case(
            "stable-version",
            Version("1.0.0") <= Version(__version__) < Version("2.0.0")
            and DomainRuntimeEngine.runtime_version == "1.0.0",
            project_version=__version__,
            domain_runtime_version=DomainRuntimeEngine.runtime_version,
        ),
        case(
            "permission-default-closed",
            all(getattr(settings, flag) is False for flag, _ in PERMISSION_BOUNDARIES)
            and all(
                token is None or getattr(settings, token) is None
                for _, token in PERMISSION_BOUNDARIES
            ),
        ),
        case(
            "audit-identity-fields",
            all(id_field in model.model_fields for _, _, model, id_field in AUDIT_RECORDS),
            record_count=len(AUDIT_RECORDS),
        ),
        case(
            "bounded-auto-disabled",
            BOUNDED_AUTO_ENABLED is False,
        ),
        case(
            "production-qualification-separated",
            manifest.status == "engineering_frozen"
            and manifest.production_qualified is False
            and bool(manifest.production_blockers),
            blocker_count=len(manifest.production_blockers),
        ),
    ]
    with tempfile.TemporaryDirectory(prefix="di-phase9-") as temp_value:
        workspace = Path(temp_value) / "var"
        app = create_app(Settings(workspace=workspace))
        actual_operations = {
            (method, route.path)
            for route in app.routes
            for method in getattr(route, "methods", set())
            if route.path == "/healthz" or route.path.startswith("/v1/")
        }
        cases.append(
            case(
                "rest-api-frozen-operations-present",
                set(FROZEN_API_OPERATIONS).issubset(actual_operations),
                operation_count=len(actual_operations),
            )
        )
        registry = DomainPackRegistry(
            workspace,
            engine_version=DomainRuntimeEngine.runtime_version,
        )
        builtins = registry.list_builtin_records()
        loadable = True
        for item in builtins:
            record = registry.install_builtin(item.pack_id)
            registry.load(record.pack_id, record.version)
        cases.append(
            case(
                "domain-pack-compatibility",
                loadable and len(builtins) == 6,
                pack_count=len(builtins),
            )
        )
        guarded = {
            "runs",
            "raw",
            "sources",
            "assets",
            "standard",
            "structures",
            "domain-packs",
            "domain-results",
            "domain-reviews",
            "family-detections",
            "rill-shadow",
            "rill-assist",
            "mlops",
            "production-qualification",
        }
        runtime_files = [
            path
            for namespace in guarded
            for path in (ROOT / "var" / namespace).rglob("*")
            if path.is_file() and path.name != ".gitkeep"
        ]
        cases.append(
            case(
                "release-runtime-state-clean",
                not runtime_files,
                files=[str(path.relative_to(ROOT)) for path in runtime_files],
            )
        )
    cases.append(
        case(
            "freeze-doc-copy-identical",
            (
                ROOT / "docs/phase-9/FROZEN_CONTRACTS_V1.json"
            ).read_bytes()
            == (
                ROOT / "src/document_intelligence/defaults/frozen_contracts_v1.json"
            ).read_bytes(),
        )
    )
    report = FreezeBenchmarkReport(
        project_version=__version__,
        manifest_digest=manifest.manifest_digest,
        contract_count=len(manifest.contracts),
        audit_record_count=len(AUDIT_RECORDS),
        api_operation_count=len(FROZEN_API_OPERATIONS),
        cases=cases,
        passed=all(item.passed for item in cases),
    )
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    rows = "\n".join(
        f"| {item.name} | {'通过' if item.passed else '失败'} |"
        for item in report.cases
    )
    MD_OUT.write_text(
        "# Phase 9：1.0冻结基准\n\n"
        f"- 项目版本：`{report.project_version}`\n"
        f"- 冻结清单摘要：`{report.manifest_digest}`\n"
        f"- 冻结契约：{report.contract_count}\n"
        f"- 审计记录格式：{report.audit_record_count}\n"
        f"- REST操作：{report.api_operation_count}\n"
        f"- 总结论：{'通过' if report.passed else '失败'}\n\n"
        "| 门禁 | 结果 |\n|---|---|\n"
        f"{rows}\n\n"
        "本基准证明工程契约与冻结清单一致，不代表真实多领域文档、外部解析器、"
        "许可证或规模压力已经取得生产资格。\n",
        encoding="utf-8",
    )
    print(report.model_dump_json(indent=2))
    if not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
