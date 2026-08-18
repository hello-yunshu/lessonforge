from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    for phase in range(1, 13):
        benchmark = ROOT / "scripts" / f"run_phase{phase}_benchmark.py"
        verifier = ROOT / "scripts" / f"verify_phase{phase}.py"
        if benchmark.is_file():
            run(benchmark)
        if verifier.is_file():
            run(verifier)
    run(ROOT / "scripts" / "static_sanity.py")
    run(ROOT / "scripts" / "verify_distribution.py")


if __name__ == "__main__":
    main()
