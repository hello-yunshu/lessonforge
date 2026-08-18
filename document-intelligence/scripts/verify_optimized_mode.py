from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase-12" / "optimized_mode.json"


def main() -> None:
    program = """
from document_intelligence import __version__
from document_intelligence.config import Settings
from document_intelligence.freeze import FreezeService
from document_intelligence.parsers import NativePdfParser
assert __version__ == '1.0.3rc1'
assert Settings().production_mode is False
assert FreezeService().verify().compatible is True
assert NativePdfParser().parser_id == 'native-pdf'
print('optimized-mode-ok')
"""
    completed = subprocess.run(
        [sys.executable, "-O", "-c", program],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        env={"PYTHONPATH": str(ROOT / "src")},
    )
    payload = {
        "phase": 12,
        "passed": completed.returncode == 0 and "optimized-mode-ok" in completed.stdout,
        "returncode": completed.returncode,
        "output": completed.stdout,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
