from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import yaml

from document_intelligence.domain_pack_sdk import load_domain_pack
from document_intelligence.domain_runtime import DomainPackRegistry, DomainRuntimeEngine
from document_intelligence.exceptions import (
    DomainExecutionError,
    DomainPackArchiveError,
    DomainPackCompatibilityError,
    DomainPackConflictError,
    DomainPackSignatureError,
    DomainPackStoreCorruptError,
    DomainResultStoreCorruptError,
    DomainReviewError,
)

OUT = ROOT / "docs" / "phase-4" / "verification.json"


def main() -> None:
    checks: list[dict[str, object]] = []
    benchmark = json.loads(
        (ROOT / "docs" / "phase-4" / "benchmark_results.json").read_text(
            encoding="utf-8"
        )
    )
    checks.append({"name": "phase4-benchmark-gate", "passed": benchmark["passed"]})
    checks.append(
        {
            "name": "fallback-has-no-domain-assertions",
            "passed": benchmark["summary"]["fallback_assertion_count"] == 0,
        }
    )
    checks.append(
        {
            "name": "domain-annotation-evidence-complete",
            "passed": benchmark["summary"]["annotation_evidence_coverage"] == 1.0,
        }
    )

    source_packs: dict[str, str] = {}
    for pack_root in sorted((ROOT / "domain-packs").iterdir()):
        if not pack_root.is_dir():
            continue
        pack = load_domain_pack(pack_root)
        source_packs[pack.manifest.id] = pack.content_digest
        copied = load_domain_pack(
            ROOT / "src" / "document_intelligence" / "defaults" / "domain_packs" / pack.manifest.id
        )
        checks.append(
            {
                "name": f"default-pack-copy-{pack.manifest.id}",
                "passed": copied.content_digest == pack.content_digest,
            }
        )
        checks.append(
            {
                "name": f"declarative-entrypoints-{pack.manifest.id}",
                "passed": all(
                    Path(value).suffix.lower() in {".yaml", ".yml", ".json"}
                    for value in pack.manifest.entrypoints.values()
                ),
            }
        )
    checks.append(
        {
            "name": "verification-packs-present",
            "passed": {"generic-document", "education-content"}.issubset(source_packs),
        }
    )

    with tempfile.TemporaryDirectory(prefix="di-phase4-verify-") as temp_value:
        registry = DomainPackRegistry(
            Path(temp_value) / "var", engine_version=DomainRuntimeEngine.runtime_version
        )
        for pack_id in sorted(source_packs):
            record = registry.install_directory(ROOT / "domain-packs" / pack_id)
            registry.activate(record.pack_id, record.version)
        records = registry.list_records()
        checks.append(
            {
                "name": "pack-install-load-activate",
                "passed": len(records) == len(source_packs)
                and all(item.active for item in records)
                and all(
                    registry.load(item.pack_id).content_digest == item.content_digest
                    for item in records
                ),
            }
        )

    schema_names = {
        "domain-pack-manifest.schema.json",
        "domain-result.schema.json",
        "labelu-review-export.schema.json",
        "labelu-review-submission.schema.json",
    }
    checks.append(
        {
            "name": "phase4-schemas-exported",
            "passed": all((ROOT / "docs" / "schema" / name).is_file() for name in schema_names),
        }
    )

    rill_schema = json.loads(
        (ROOT / "configs" / "rill_observe.schema.json").read_text(encoding="utf-8")
    )
    signals_ref = rill_schema["properties"]["signals"]["$ref"].split("/")[-1]
    signal_properties = rill_schema["$defs"][signals_ref]["properties"]
    checks.append(
        {
            "name": "rill-domain-signals-shadow-only",
            "passed": rill_schema["properties"]["schema_version"]["const"]
            in {"0.4", "0.5", "0.6", "0.7", "0.8"}
            and rill_schema["properties"]["shadow_only"]["const"] is True
            and "domain" in signal_properties,
        }
    )

    runtime_namespaces = ("domain-packs", "domain-results", "domain-reviews")
    for namespace in runtime_namespaces:
        files = [
            path
            for path in (ROOT / "var" / namespace).rglob("*")
            if path.is_file()
            and path.name != ".gitkeep"
            and not (namespace == "domain-packs" and path.name == "state.json")
        ]
        checks.append(
            {"name": f"release-{namespace}-clean", "passed": not files, "files": files}
        )
    state_path = ROOT / "var" / "domain-packs" / "state.json"
    state_clean = True
    if state_path.exists():
        state_clean = json.loads(state_path.read_text(encoding="utf-8")) == {
            "version": 1,
            "active": {},
        }
    checks.append({"name": "release-domain-pack-state-empty", "passed": state_clean})

    taxonomy = yaml.safe_load(
        (ROOT / "configs" / "error_taxonomy.yaml").read_text(encoding="utf-8")
    )
    categories = taxonomy.get("categories", {})
    errors = [
        DomainPackArchiveError,
        DomainPackCompatibilityError,
        DomainPackSignatureError,
        DomainPackConflictError,
        DomainPackStoreCorruptError,
        DomainExecutionError,
        DomainResultStoreCorruptError,
        DomainReviewError,
    ]
    checks.append(
        {
            "name": "phase4-errors-in-taxonomy",
            "passed": all(categories.get(error.code) == error.severity for error in errors),
        }
    )

    payload = {
        "phase": 4,
        "passed": all(bool(check["passed"]) for check in checks),
        "checks": checks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
