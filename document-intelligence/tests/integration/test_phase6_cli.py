from __future__ import annotations

import json

import pytest

from document_intelligence.cli import main
from document_intelligence.exceptions import RillAssistDisabledError


def test_assist_cli_inspect_is_read_only(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setenv("DI_WORKSPACE", str(tmp_path / "var"))
    monkeypatch.setattr("sys.argv", ["doc-intelligence", "rill-assist-inspect"])
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["boundedAuto"] is False
    assert payload["activeActivations"] == []


def test_assist_cli_execution_defaults_to_deny(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DI_WORKSPACE", str(tmp_path / "var"))
    monkeypatch.setattr(
        "sys.argv",
        ["doc-intelligence", "rill-assist-execute", "activation", "evaluation"],
    )
    with pytest.raises(RillAssistDisabledError):
        main()
