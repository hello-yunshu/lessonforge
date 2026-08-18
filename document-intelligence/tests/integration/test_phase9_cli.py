from __future__ import annotations

import json

from document_intelligence.cli import main


def test_freeze_inspect_cli(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr("sys.argv", ["doc-intelligence", "freeze-inspect"])
    monkeypatch.setenv("DI_WORKSPACE", str(tmp_path / "var"))
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["project_version"] == "1.0.0"
    assert payload["production_qualified"] is False


def test_freeze_verify_cli(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr("sys.argv", ["doc-intelligence", "freeze-verify"])
    monkeypatch.setenv("DI_WORKSPACE", str(tmp_path / "var"))
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["compatible"] is True
    assert payload["exact_match"] is True
