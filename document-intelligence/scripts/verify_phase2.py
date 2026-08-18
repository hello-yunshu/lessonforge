from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import yaml

from pydantic import ValidationError

from document_intelligence.config import Settings
from document_intelligence.exceptions import (
    MatchInputError,
    RunStoreCorruptError,
    StandardAccessDeniedError,
    StandardApprovalError,
    StandardStoreCorruptError,
    StandardWriteDisabledError,
)
from document_intelligence.matching import StandardLibrary
from document_intelligence.parsers import NativePdfParser
from document_intelligence.schema import ParseRequest, ParserResult
from document_intelligence.services import ArtifactStore

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase-2" / "verification.json"


def main() -> None:
    checks: list[dict[str, object]] = []
    fixture = ROOT / "tests" / "fixtures" / "native_text.pdf"
    content = fixture.read_bytes()
    parser = NativePdfParser()
    first = parser.parse(
        ParseRequest(
            filename="first.pdf",
            mime_type="application/pdf",
            content=content,
            domain_pack="alpha",
        )
    )
    second = parser.parse(
        ParseRequest(
            filename="second.pdf",
            mime_type="application/pdf",
            content=content,
            domain_pack="beta",
        )
    )
    checks.append(
        {
            "name": "request-context-prevents-run-id-collision",
            "passed": first.run.parse_run_id != second.run.parse_run_id,
        }
    )

    unsafe_payload = first.model_dump(mode="python")
    unsafe_payload["run"]["parse_run_id"] = ".."
    unsafe_payload["document"]["parse_run_id"] = ".."
    for item in unsafe_payload["document"]["evidence"]:
        item["parse_run_id"] = ".."
    unsafe_rejected = False
    try:
        ParserResult.model_validate(unsafe_payload)
    except ValidationError:
        unsafe_rejected = True
    checks.append({"name": "unsafe-identifiers-rejected", "passed": unsafe_rejected})

    with tempfile.TemporaryDirectory(prefix="di-phase2-verify-") as temp:
        store = ArtifactStore(Path(temp) / "var")
        request = ParseRequest(
            filename=fixture.name,
            mime_type="application/pdf",
            content=content,
        )
        result = parser.parse(request)
        store.commit_success(request, result)
        loaded = store.read_result(result.run.parse_run_id)
        checks.append(
            {
                "name": "source-retained-by-content-address",
                "passed": bool(loaded.document.source.source_ref)
                and store.read_source(loaded.document.source.source_ref or "") == content,
            }
        )
        library = StandardLibrary(store)
        manifest = library.register_run(
            result.run.parse_run_id,
            reviewer="phase2-verifier",
            approval_note="integrity verification fixture",
            approved=True,
        )
        document_path = library.documents_dir / manifest.standard_id / "document.json"
        checks.append(
            {
                "name": "standard-document-digest-bound",
                "passed": hashlib.sha256(document_path.read_bytes()).hexdigest()
                == manifest.document_sha256
                and library.read_document(manifest.standard_id).document_id
                == manifest.document_id,
            }
        )

    benchmark = json.loads(
        (ROOT / "docs" / "phase-2" / "benchmark_results.json").read_text(encoding="utf-8")
    )
    checks.append({"name": "matching-regression-gate", "passed": benchmark["passed"]})
    checks.append(
        {
            "name": "unknown-never-force-standard",
            "passed": benchmark["summary"]["negative_false_accepts"] == 0,
        }
    )
    settings = Settings.from_env()
    checks.append(
        {
            "name": "standard-writes-default-disabled",
            "passed": settings.enable_standard_writes is False,
        }
    )
    checks.append(
        {
            "name": "standard-access-default-denied",
            "passed": settings.standard_access_token_sha256 is None,
        }
    )
    standard_files = [
        path
        for path in (ROOT / "var" / "standard").rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    ]
    checks.append({"name": "release-standard-store-clean", "passed": not standard_files})
    rill_schema = json.loads(
        (ROOT / "configs" / "rill_observe.schema.json").read_text(encoding="utf-8")
    )
    checks.append(
        {
            "name": "rill-remains-shadow-only",
            "passed": rill_schema["properties"]["shadow_only"].get("const") is True,
        }
    )
    license_inventory = yaml.safe_load(
        (ROOT / "configs" / "third_party_licenses.yaml").read_text(encoding="utf-8")
    )
    runtime_components = license_inventory.get("runtime_components", [])
    optional_components = license_inventory.get("optional_components", [])
    pypdf = next(
        (item for item in runtime_components if item.get("name") == "pypdf"),
        None,
    )
    pymupdf = next(
        (item for item in optional_components if item.get("name") == "PyMuPDF"),
        None,
    )
    checks.append(
        {
            "name": "native-pdf-license-route-cleared",
            "passed": bool(pypdf)
            and pypdf.get("license") == "BSD-3-Clause"
            and pypdf.get("blocker") is False,
        }
    )
    checks.append(
        {
            "name": "optional-pymupdf-license-blocker-explicit",
            "passed": bool(pymupdf)
            and pymupdf.get("production_review") == "mandatory"
            and pymupdf.get("blocker") is True,
        }
    )
    expected_runtime_dirs = ["runs", "raw", "sources", "assets", "standard"]
    checks.append(
        {
            "name": "runtime-store-layout-preserved",
            "passed": all(
                (ROOT / "var" / name / ".gitkeep").is_file()
                for name in expected_runtime_dirs
            ),
        }
    )
    expected_error_levels = {
        RunStoreCorruptError.code: RunStoreCorruptError.severity,
        StandardAccessDeniedError.code: StandardAccessDeniedError.severity,
        StandardWriteDisabledError.code: StandardWriteDisabledError.severity,
        StandardApprovalError.code: StandardApprovalError.severity,
        StandardStoreCorruptError.code: StandardStoreCorruptError.severity,
        MatchInputError.code: MatchInputError.severity,
    }
    taxonomy = yaml.safe_load(
        (ROOT / "configs" / "error_taxonomy.yaml").read_text(encoding="utf-8")
    )
    categories = taxonomy.get("categories", {})
    checks.append(
        {
            "name": "error-taxonomy-matches-runtime-exceptions",
            "passed": all(
                categories.get(code) == severity
                for code, severity in expected_error_levels.items()
            ),
        }
    )
    payload = {
        "phase": 2,
        "passed": all(bool(check["passed"]) for check in checks),
        "checks": checks,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
