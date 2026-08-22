from __future__ import annotations

import hashlib

from document_intelligence.rill.adoption import ReleaseArtifact, load_adoption_lock
from document_intelligence.rill.distribution import RillRuntimeManager


def artifact(data: bytes) -> ReleaseArtifact:
    return ReleaseArtifact(
        kind="runtime",
        id="rill-runtime",
        version="1.2.0",
        runtimeApiVersion=2,
        targetOs="linux",
        targetArch="x86_64",
        targetLibc="gnu",
        url="https://github.com/hello-yunshu/rill-ml/releases/download/v1.2.0/rill-runtime-1.2.0-linux-x86_64",
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
    )


def test_stage_probe_activate_and_rollback_preserves_previous_good(tmp_path) -> None:
    manager = RillRuntimeManager(tmp_path)
    lock = load_adoption_lock()
    first = b"#!/usr/bin/env python3\nprint('1.2.0')\n"
    first_artifact = artifact(first)
    first_staged = manager.stage_bytes(first, first_artifact)
    first_path = manager.activate(first_staged, first_artifact, lock=lock)
    assert manager.active()["sha256"] == first_artifact.sha256

    second = b"#!/usr/bin/env python3\nprint('replacement')\n"
    second_artifact = artifact(second)
    second_staged = manager.stage_bytes(second, second_artifact)
    second_path = manager.activate(second_staged, second_artifact, lock=lock)
    assert second_path != first_path
    assert manager.active()["sha256"] == second_artifact.sha256

    rollback_path = manager.rollback()
    assert rollback_path == first_path
    assert manager.active()["sha256"] == first_artifact.sha256
    assert first_path.read_bytes() == first
