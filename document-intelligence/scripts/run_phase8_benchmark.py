from __future__ import annotations

import json
from pathlib import Path

from document_intelligence.domain_regression import CrossDomainRegressionRunner

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    runner = CrossDomainRegressionRunner(
        [path for path in sorted((ROOT / "domain-packs").iterdir()) if path.is_dir()]
    )
    suite = runner.load_suite(ROOT / "examples" / "domain-fixtures" / "suite.yaml")
    report = runner.run(suite)
    output = ROOT / "docs" / "phase-8" / "CROSS_DOMAIN_BENCHMARK.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
