from __future__ import annotations

import json
from pathlib import Path

import pytest

from document_intelligence.cli import main
from document_intelligence.domain_pack_sdk import load_domain_pack
from document_intelligence.exceptions import DomainPackWriteDisabledError


def test_phase8_cli_lists_builtins_and_creates_scaffold(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    monkeypatch.setenv("DI_WORKSPACE", str(tmp_path / "var"))
    monkeypatch.setattr("sys.argv", ["doc-intelligence", "domain-pack-builtin-list"])
    assert main() == 0
    listed = json.loads(capsys.readouterr().out)
    assert len(listed) == 6
    assert sum(item["has_family_profile"] for item in listed) == 5

    target = tmp_path / "templates"
    monkeypatch.setattr(
        "sys.argv",
        [
            "doc-intelligence",
            "domain-pack-scaffold",
            str(target),
            "--id",
            "example-domain",
            "--template",
            "relation-heavy",
        ],
    )
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    pack = load_domain_pack(Path(payload["path"]))
    assert pack.family is not None
    assert pack.manifest.id == "example-domain"


def test_builtin_install_cli_defaults_to_deny(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DI_WORKSPACE", str(tmp_path / "var"))
    monkeypatch.setattr(
        "sys.argv",
        ["doc-intelligence", "domain-pack-install-builtin", "technical-manual"],
    )
    with pytest.raises(DomainPackWriteDisabledError):
        main()
