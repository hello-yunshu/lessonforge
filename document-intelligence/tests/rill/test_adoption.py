from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from document_intelligence.rill.adoption import (
    RillAdoptionLock,
    RillDistributionError,
    canonical_json,
    parse_and_verify_release_index,
    resolve_target,
    select_runtime,
    verify_release_index_identity,
)


def lock(key: str) -> RillAdoptionLock:
    return RillAdoptionLock.model_validate(
        {
            "upstreamRepository": "hello-yunshu/rill-ml",
            "supported": "1.2.0",
            "tested": "1.2.0",
            "tag": "v1.2.0",
            "commit": "dc96fdb3bf55eacdd1c093f1be08d1c9daed4400",
            "releaseIndexSchema": 3,
            "stableRuntimeApi": 2,
            "productionProtocol": "stable-v2",
            "upstreamLatest": "1.3.0",
            "upstreamLatestInformationalOnly": True,
            "releaseIndexSha256": "0" * 64,
            "trust": {
                "releaseIndex": {"test-key": key},
                "model": {"test-key": key},
                "handler": {"test-key": key},
            },
            "qualification": {},
        }
    )


def signed_index(private: Ed25519PrivateKey) -> bytes:
    payload = {
        "schemaVersion": 3,
        "channel": "stable",
        "generatedAt": "2026-08-22T00:00:00Z",
        "publisherKeyId": "test-key",
        "artifacts": [
            {
                "kind": "runtime",
                "id": "rill-runtime",
                "version": "1.2.0",
                "runtimeApiVersion": 2,
                "targetOs": "linux",
                "targetArch": "x86_64",
                "targetLibc": "gnu",
                "url": "https://github.com/hello-yunshu/rill-ml/releases/download/v1.2.0/rill-runtime-1.2.0-linux-x86_64",
                "sha256": "a" * 64,
                "size": 10,
            }
        ],
    }
    signature = private.sign(canonical_json(payload)).hex()
    return json.dumps({"payload": payload, "signature": signature}).encode()


def test_real_lock_is_immutable_and_v3_is_not_production() -> None:
    from document_intelligence.rill.adoption import load_adoption_lock

    adoption = load_adoption_lock()
    assert adoption.supported == adoption.tested == "1.2.0"
    assert adoption.commit == "dc96fdb3bf55eacdd1c093f1be08d1c9daed4400"
    assert adoption.production_protocol == "stable-v2"


def test_release_index_signature_and_identity_are_strict() -> None:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes_raw().hex()
    adoption = lock(public)
    index = parse_and_verify_release_index(signed_index(private), lock=adoption)
    verify_release_index_identity(index, lock=adoption)
    assert (
        select_runtime(index, target=("linux", "x86_64", "gnu"), lock=adoption).id == "rill-runtime"
    )

    bad = json.loads(signed_index(private))
    bad["signature"] = "0" * 128
    with pytest.raises(RillDistributionError) as exc:
        parse_and_verify_release_index(json.dumps(bad).encode(), lock=adoption)
    assert exc.value.reason_code == "RILL_INDEX_SIGNATURE_INVALID"


def test_target_resolver_rejects_unknown_libc_and_distinguishes_musl() -> None:
    assert resolve_target(system="Linux", machine="x86_64", libc="glibc") == (
        "linux",
        "x86_64",
        "gnu",
    )
    assert resolve_target(system="Linux", machine="x86_64", libc="musl") == (
        "linux",
        "x86_64",
        "musl",
    )
    with pytest.raises(RillDistributionError) as exc:
        resolve_target(system="Linux", machine="x86_64", libc="unknown")
    assert exc.value.reason_code == "RILL_UNSUPPORTED_LIBC"
