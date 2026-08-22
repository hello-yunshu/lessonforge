"""Compare the vendored Handler ABI with the pinned upstream v1.2.0 WIT."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "rill-handler" / "wit" / "rill-handler.wit"
LOCK = ROOT / "rill-handler" / "wit-contract.json"


def normalized_sha256(path: Path) -> str:
    text = re.sub(r"//[^\n]*", "", path.read_text(encoding="utf-8"))
    return hashlib.sha256("".join(text.split()).encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical", type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    expected = str(lock["normalizedSha256"])
    local_digest = normalized_sha256(LOCAL)
    canonical_digest = normalized_sha256(args.canonical)
    if local_digest != expected or canonical_digest != expected or local_digest != canonical_digest:
        raise SystemExit(
            "Handler WIT contract mismatch: "
            f"local={local_digest} canonical={canonical_digest} expected={expected}"
        )
    print(json.dumps({"status": "PASS", "normalizedSha256": expected}, sort_keys=True))


if __name__ == "__main__":
    main()
