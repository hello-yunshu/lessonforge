from __future__ import annotations

import json
import sys

from document_intelligence.cli import main


def test_cli_structure_recover_and_get(monkeypatch, tmp_path, fixtures_dir) -> None:
    monkeypatch.setenv("DI_WORKSPACE", str(tmp_path / "var"))
    monkeypatch.delenv("DI_PARSER_CONFIG", raising=False)
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
    run_id = json.loads(parsed_output.read_text(encoding="utf-8"))["run"][
        "parse_run_id"
    ]
    structure_output = tmp_path / "structure.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "doc-intelligence",
            "structure-recover",
            run_id,
            "--output",
            str(structure_output),
        ],
    )
    assert main() == 0
    structure_id = json.loads(structure_output.read_text(encoding="utf-8"))[
        "structure_id"
    ]
    fetched_output = tmp_path / "fetched.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "doc-intelligence",
            "structure-get",
            structure_id,
            "--output",
            str(fetched_output),
        ],
    )
    assert main() == 0
    assert json.loads(fetched_output.read_text(encoding="utf-8"))[
        "structure_id"
    ] == structure_id
