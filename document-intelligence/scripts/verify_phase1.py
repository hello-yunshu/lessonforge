from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import yaml

from document_intelligence.config import load_parser_config
from document_intelligence.domain_pack_sdk import load_domain_pack
from document_intelligence.schema import ParsedDocument

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase-1" / "verification.json"


def check_python_sources() -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    forbidden_calls = {"eval", "exec"}
    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in forbidden_calls:
                    findings.append({"file": str(path.relative_to(ROOT)), "call": node.func.id})
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"system", "popen"}:
                    findings.append({"file": str(path.relative_to(ROOT)), "call": node.func.attr})
    return findings


def main() -> None:
    checks: list[dict[str, object]] = []

    schema = ParsedDocument.model_json_schema()
    checks.append({"name": "schema-exportable", "passed": bool(schema.get("properties"))})

    pack = load_domain_pack(ROOT / "domain-packs" / "generic-document")
    checks.append({"name": "generic-domain-pack", "passed": pack.manifest.id == "generic-document"})

    parser_config = load_parser_config(ROOT / "configs" / "parsers.yaml")
    external_safe = True
    for parser_id in ("paddle", "opendoc", "mineru-benchmark"):
        config = parser_config.parsers[parser_id]
        if config.enabled:
            external_safe = external_safe and bool(
                config.required_artifact_sha256
                and re.fullmatch(r"[0-9a-f]{64}", config.required_artifact_sha256)
            )
    checks.append({"name": "external-parser-fail-closed", "passed": external_safe})

    error_taxonomy = yaml.safe_load(
        (ROOT / "configs" / "error_taxonomy.yaml").read_text(encoding="utf-8")
    )
    checks.append(
        {
            "name": "p0-never-auto-accept",
            "passed": error_taxonomy["levels"]["P0"]["auto_accept"] is False,
        }
    )

    rill_schema = json.loads(
        (ROOT / "configs" / "rill_observe.schema.json").read_text(encoding="utf-8")
    )
    checks.append(
        {
            "name": "rill-shadow-only",
            "passed": rill_schema["properties"]["shadow_only"].get("const") is True,
        }
    )

    standard_files = [
        path
        for path in (ROOT / "var" / "standard").rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    ]
    checks.append({"name": "standard-result-clean", "passed": not standard_files})

    dangerous = check_python_sources()
    checks.append({"name": "no-eval-exec-shell", "passed": not dangerous, "findings": dangerous})

    core_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in sorted((ROOT / "src" / "document_intelligence").rglob("*.py"))
    )
    domain_terms = [
        term for term in ["教材", "例题", "合同条款", "课时"] if term in core_text
    ]
    checks.append(
        {"name": "core-domain-neutral", "passed": not domain_terms, "findings": domain_terms}
    )

    payload = {
        "phase": 1,
        "passed": all(bool(check["passed"]) for check in checks),
        "checks": checks,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not payload["passed"]:
        raise SystemExit(1)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
