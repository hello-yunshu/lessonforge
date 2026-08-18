from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase-12" / "test_budget.json"
BATCH_TIMEOUT_SECONDS = 120
TOTAL_BUDGET_SECONDS = 600
BATCHES = [
    [
        "tests/campaign",
        "tests/contract",
        "tests/domain_pack_sdk",
        "tests/domain_regression",
        "tests/domain_runtime",
        "tests/family",
        "tests/freeze",
        "tests/golden",
    ],
    ["tests/matching", "tests/mlops", "tests/production", "tests/review", "tests/rill"],
    ["tests/security", "tests/structure", "tests/unit"],
    ["tests/integration"],
]


def main() -> None:
    started = time.monotonic()
    records: list[dict[str, object]] = []
    for index, batch in enumerate(BATCHES, start=1):
        if time.monotonic() - started >= TOTAL_BUDGET_SECONDS:
            raise RuntimeError("test budget exceeded before all batches completed")
        batch_started = time.monotonic()
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", *batch],
                cwd=ROOT,
                timeout=BATCH_TIMEOUT_SECONDS,
                check=False,
                env={**os.environ, "PYTHONPATH": f"{ROOT / 'src'}:{ROOT}"},
            )
        except subprocess.TimeoutExpired:
            records.append(
                {
                    "batch": index,
                    "targets": batch,
                    "passed": False,
                    "timed_out": True,
                    "duration_seconds": round(time.monotonic() - batch_started, 3),
                }
            )
            break
        records.append(
            {
                "batch": index,
                "targets": batch,
                "passed": completed.returncode == 0,
                "timed_out": False,
                "duration_seconds": round(time.monotonic() - batch_started, 3),
            }
        )
        if completed.returncode != 0:
            break
    payload = {
        "phase": 12,
        "passed": len(records) == len(BATCHES)
        and all(bool(item["passed"]) for item in records),
        "test_files": len(list((ROOT / "tests").rglob("test_*.py"))),
        "completed_batches": len(records),
        "batch_count": len(BATCHES),
        "batch_timeout_seconds": BATCH_TIMEOUT_SECONDS,
        "total_budget_seconds": TOTAL_BUDGET_SECONDS,
        "duration_seconds": round(time.monotonic() - started, 3),
        "records": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    summary = {key: value for key, value in payload.items() if key != "records"}
    print(json.dumps(summary, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
