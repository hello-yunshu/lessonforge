from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.workspace_backup import create_backup, restore_backup, verify_backup


def test_workspace_backup_roundtrip_and_tamper_detection(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "runs" / "one").mkdir(parents=True)
    (workspace / "runs" / "one" / "result.json").write_text(
        '{"ok":true}', encoding="utf-8"
    )
    archive = tmp_path / "backup.zip"
    first = create_backup(workspace, archive)
    second = verify_backup(archive)
    assert first == second
    restored = tmp_path / "restored"
    restore_backup(archive, restored)
    assert (restored / "runs" / "one" / "result.json").read_text() == '{"ok":true}'
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "data/runs/one/result.json":
                data = b"tampered"
            target.writestr(info, data)
    with pytest.raises(ValueError):
        verify_backup(tampered)


def test_workspace_backup_rejects_symlinks(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = tmp_path / "outside"
    target.write_text("secret", encoding="utf-8")
    try:
        (workspace / "link").symlink_to(target)
    except OSError:
        pytest.skip("symlinks are not supported")
    with pytest.raises(ValueError, match="symlink"):
        create_backup(workspace, tmp_path / "backup.zip")
