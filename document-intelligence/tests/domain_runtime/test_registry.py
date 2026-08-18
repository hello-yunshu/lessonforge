from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
import yaml

from document_intelligence.domain_runtime import DomainPackRegistry
from document_intelligence.exceptions import (
    DomainPackArchiveError,
    DomainPackCompatibilityError,
    DomainPackConflictError,
    DomainPackSignatureError,
    DomainPackStoreCorruptError,
)

from .helpers import archive_directory, copy_pack, sign_pack


def registry(tmp_path: Path, **kwargs) -> DomainPackRegistry:
    return DomainPackRegistry(tmp_path / "var", engine_version="0.4.0", **kwargs)




def test_registry_initialization_does_not_persist_empty_state(tmp_path) -> None:
    store = registry(tmp_path)
    assert store.state_path.exists() is False
    assert store.list_records() == []
    assert store.state_path.exists() is False


def test_missing_state_is_default_but_symlink_is_rejected(tmp_path) -> None:
    store = registry(tmp_path)
    target = tmp_path / "external-state.json"
    target.write_text('{"version": 1, "active": {}}', encoding="utf-8")
    store.state_path.symlink_to(target)
    with pytest.raises(DomainPackStoreCorruptError):
        store.list_records()

def test_install_activate_deactivate_and_uninstall(tmp_path) -> None:
    pack = copy_pack(tmp_path)
    store = registry(tmp_path)
    record = store.install_archive(archive_directory(pack))
    assert record.pack_id == "education-content"
    assert record.active is False
    assert store.activate(record.pack_id, record.version).active is True
    assert store.load(record.pack_id).manifest.version == record.version
    with pytest.raises(DomainPackConflictError):
        store.uninstall(record.pack_id, record.version)
    store.deactivate(record.pack_id)
    store.uninstall(record.pack_id, record.version)
    assert store.list_records() == []


def test_same_version_with_different_content_is_rejected(tmp_path) -> None:
    pack = copy_pack(tmp_path)
    store = registry(tmp_path)
    store.install_archive(archive_directory(pack))
    labels = pack / "labels.yaml"
    labels.write_text(labels.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    manifest = yaml.safe_load((pack / "manifest.yaml").read_text(encoding="utf-8"))
    import hashlib
    manifest["file_digests"]["labels.yaml"] = hashlib.sha256(labels.read_bytes()).hexdigest()
    (pack / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    with pytest.raises(DomainPackConflictError):
        store.install_archive(archive_directory(pack))


def test_incompatible_pack_is_rejected(tmp_path) -> None:
    pack = copy_pack(tmp_path)
    path = pack / "manifest.yaml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    manifest["core_schema"] = ">=9,<10"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    with pytest.raises(DomainPackCompatibilityError):
        registry(tmp_path).install_archive(archive_directory(pack))


def test_archive_path_traversal_is_rejected(tmp_path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../manifest.yaml", "id: unsafe")
    with pytest.raises(DomainPackArchiveError):
        registry(tmp_path).install_archive(buffer.getvalue())


def test_archive_compression_bomb_is_rejected(tmp_path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.yaml", b"0" * 100000)
    with pytest.raises(DomainPackArchiveError, match="compression ratio"):
        registry(tmp_path, max_compression_ratio=2).install_archive(buffer.getvalue())


def test_signature_is_required_and_verified(tmp_path) -> None:
    unsigned = copy_pack(tmp_path / "unsigned")
    with pytest.raises(DomainPackSignatureError):
        registry(tmp_path / "required", require_signatures=True).install_archive(
            archive_directory(unsigned)
        )
    signed = copy_pack(tmp_path / "signed")
    archive, public_key = sign_pack(signed)
    store = registry(
        tmp_path / "trusted",
        require_signatures=True,
        trusted_public_keys={"test-key": public_key},
    )
    assert store.install_archive(archive).signature_verified is True


def test_installed_pack_tampering_is_detected(tmp_path) -> None:
    pack = copy_pack(tmp_path)
    store = registry(tmp_path)
    record = store.install_archive(archive_directory(pack))
    installed = store.packs_dir / record.pack_id / record.version / "labels.yaml"
    installed.write_text("tampered: true\n", encoding="utf-8")
    with pytest.raises(DomainPackStoreCorruptError):
        store.load(record.pack_id, record.version)


def test_incompatible_historical_pack_can_be_listed_and_uninstalled(tmp_path) -> None:
    pack = copy_pack(tmp_path)
    manifest_path = pack / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["engine"] = ">=0.4,<1.0"
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )
    original = registry(tmp_path)
    record = original.install_archive(archive_directory(pack))
    upgraded = DomainPackRegistry(tmp_path / "var", engine_version="1.0.0")
    listed = upgraded.list_records()
    assert [(item.pack_id, item.version) for item in listed] == [(record.pack_id, record.version)]
    with pytest.raises(DomainPackCompatibilityError):
        upgraded.load(record.pack_id, record.version)
    upgraded.uninstall(record.pack_id, record.version)
    assert upgraded.list_records() == []
