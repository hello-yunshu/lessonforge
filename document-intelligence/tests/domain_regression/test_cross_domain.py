from __future__ import annotations

import hashlib
import json
from pathlib import Path

from document_intelligence.domain_regression import CrossDomainRegressionRunner
from document_intelligence.schema import ParsedDocument

ROOT = Path(__file__).resolve().parents[2]


def test_cross_domain_suite_preserves_core_schema_and_isolates_domains() -> None:
    roots = sorted(path for path in (ROOT / "domain-packs").iterdir() if path.is_dir())
    runner = CrossDomainRegressionRunner(roots)
    suite = runner.load_suite(ROOT / "examples" / "domain-fixtures" / "suite.yaml")
    report = runner.run(suite)
    assert report.passed is True
    assert report.total_cases == 5
    assert report.passed_cases == 5
    assert report.family_accuracy == 1.0
    assert report.bounded_auto is False
    assert all(case.source_unchanged for case in report.cases)
    assert all(case.evidence_complete for case in report.cases)
    assert all(case.isolated_results for case in report.cases)
    current = hashlib.sha256(
        json.dumps(
            ParsedDocument.model_json_schema(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert current == suite.core_schema_sha256
