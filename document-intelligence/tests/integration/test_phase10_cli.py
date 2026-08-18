from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_production_cli_inspect_has_no_qualification(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    env["DI_WORKSPACE"] = str(tmp_path / "var")
    result = subprocess.run(
        [sys.executable, "-m", "document_intelligence.cli", "production-inspect"],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["qualifiedReportCount"] == 0
    assert payload["automaticReleaseAuthorized"] is False
    assert payload["boundedAuto"] is False
