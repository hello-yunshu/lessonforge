from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

from document_intelligence.rill.adoption import (
    MAX_RELEASE_INDEX_BYTES,
    load_adoption_lock,
    parse_and_verify_release_index,
    verify_release_index_identity,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the immutable RillML 1.2.0 release index")
    parser.add_argument("--index", type=Path)
    args = parser.parse_args()
    lock = load_adoption_lock()
    if args.index:
        raw = args.index.read_bytes()
    else:
        url = f"https://github.com/{lock.upstream_repository}/releases/download/{lock.tag}/stable-index.json"
        with urllib.request.urlopen(url, timeout=30) as response:
            raw = response.read(MAX_RELEASE_INDEX_BYTES + 1)
    index = parse_and_verify_release_index(raw, lock=lock)
    verify_release_index_identity(index, lock=lock)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != lock.release_index_sha256:
        raise SystemExit("stable-index.json digest differs from the immutable adoption lock")
    print(
        json.dumps(
            {
                "status": "PASS",
                "tag": lock.tag,
                "commit": lock.commit,
                "indexSha256": digest,
                "schemaVersion": index.payload.schema_version,
                "channel": index.payload.channel,
                "artifacts": len(index.payload.artifacts),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
