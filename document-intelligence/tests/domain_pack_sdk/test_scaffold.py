from __future__ import annotations

from pathlib import Path

import pytest

from document_intelligence.domain_pack_sdk import (
    DomainPackTemplateKind,
    create_domain_pack_scaffold,
    load_domain_pack,
)


@pytest.mark.parametrize("kind", list(DomainPackTemplateKind))
def test_scaffold_is_declarative_loadable_and_digest_complete(
    tmp_path: Path, kind: DomainPackTemplateKind
) -> None:
    root = create_domain_pack_scaffold(
        tmp_path,
        pack_id=f"sample-{kind.value}",
        template=kind,
    )
    pack = load_domain_pack(root)
    assert pack.manifest.id == f"sample-{kind.value}"
    assert pack.family is not None
    assert pack.family.family_id == pack.manifest.id
    assert "family-detection-metadata" in pack.manifest.permissions
    assert not list(root.rglob("*.py"))
    assert set(pack.manifest.file_digests) == {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "manifest.yaml"
    }


def test_scaffold_rejects_existing_or_unsafe_target(tmp_path: Path) -> None:
    create_domain_pack_scaffold(tmp_path, pack_id="safe-pack")
    with pytest.raises(FileExistsError):
        create_domain_pack_scaffold(tmp_path, pack_id="safe-pack")
    with pytest.raises(ValueError):
        create_domain_pack_scaffold(tmp_path, pack_id="Unsafe_pack")
