from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from document_intelligence.domain_pack_sdk import DomainPackManifest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--private-key", type=Path)
    parser.add_argument("--key-id")
    args = parser.parse_args()
    root = args.root.resolve()
    manifest_path = root / "manifest.yaml"
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    raw["file_digests"] = {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "manifest.yaml" and not path.is_symlink()
    }
    raw["signing_key_id"] = None
    raw["signature"] = None
    manifest = DomainPackManifest.model_validate(raw)
    if args.private_key:
        if not args.key_id:
            parser.error("--key-id is required with --private-key")
        private_bytes = args.private_key.read_bytes()
        try:
            key = serialization.load_pem_private_key(private_bytes, password=None)
        except ValueError:
            key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_bytes))
        if not isinstance(key, Ed25519PrivateKey):
            parser.error("private key is not Ed25519")
        raw["signing_key_id"] = args.key_id
        unsigned = DomainPackManifest.model_construct(**raw)
        raw["signature"] = base64.b64encode(
            key.sign(unsigned.canonical_signing_payload())
        ).decode("ascii")
        manifest = DomainPackManifest.model_validate(raw)
    manifest_path.write_text(
        yaml.safe_dump(
            manifest.model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(manifest.canonical_signing_payload()).hexdigest()
    print(manifest.id, manifest.version, digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
