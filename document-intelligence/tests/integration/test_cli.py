from __future__ import annotations

import json
import sys

from document_intelligence.cli import main


def _configure(monkeypatch, tmp_path) -> None:
    root = tmp_path / "var"
    monkeypatch.setenv("DI_WORKSPACE", str(root))
    monkeypatch.delenv("DI_PARSER_CONFIG", raising=False)


def test_cli_parse_register_list_and_match(monkeypatch, tmp_path, fixtures_dir, capsys) -> None:
    _configure(monkeypatch, tmp_path)
    source = fixtures_dir / "native_text.pdf"
    parsed_output = tmp_path / "parsed.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "doc-intelligence",
            "parse",
            str(source),
            "--parser",
            "native-pdf",
            "--output",
            str(parsed_output),
        ],
    )
    assert main() == 0
    parsed = json.loads(parsed_output.read_text(encoding="utf-8"))
    run_id = parsed["run"]["parse_run_id"]

    monkeypatch.setenv("DI_ENABLE_STANDARD_WRITES", "true")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "doc-intelligence",
            "standard-register",
            run_id,
            "--reviewer",
            "cli-reviewer",
            "--note",
            "approved CLI fixture",
            "--approved",
        ],
    )
    assert main() == 0
    registered = json.loads(capsys.readouterr().out)
    assert registered["standard_id"].startswith("std_")

    monkeypatch.setattr(sys, "argv", ["doc-intelligence", "standard-list"])
    assert main() == 0
    listed = json.loads(capsys.readouterr().out)
    assert len(listed) == 1

    match_output = tmp_path / "match.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "doc-intelligence",
            "match",
            str(source),
            "--include-standard",
            "--output",
            str(match_output),
        ],
    )
    assert main() == 0
    matched = json.loads(match_output.read_text(encoding="utf-8"))
    assert matched["match"]["decision"] == "safe_standard_reuse"
    assert matched["standard_document"]["source"]["sha256"] == (
        parsed["document"]["source"]["sha256"]
    )


def test_cli_parsers(monkeypatch, tmp_path, capsys) -> None:
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["doc-intelligence", "parsers"])
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(item["parser_id"] == "native-pdf" for item in payload)
