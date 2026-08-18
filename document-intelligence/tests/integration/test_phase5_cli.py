from __future__ import annotations

import json

import pytest

from document_intelligence.cli import main
from document_intelligence.exceptions import RillWriteDisabledError


def test_rill_shadow_cli_inspect_is_read_only(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setenv("DI_WORKSPACE", str(tmp_path / "var"))
    monkeypatch.setenv("DI_RILL_SHADOW_BACKEND", "disabled")
    monkeypatch.setattr("sys.argv", ["doc-intelligence", "rill-shadow-inspect"])
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["shadowOnly"] is True
    assert payload["noProductionActions"] is True


def test_rill_shadow_cli_write_defaults_to_deny(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DI_WORKSPACE", str(tmp_path / "var"))
    monkeypatch.setattr(
        "sys.argv", ["doc-intelligence", "rill-shadow-evaluate", "run-missing"]
    )
    with pytest.raises(RillWriteDisabledError):
        main()
