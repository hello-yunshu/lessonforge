from __future__ import annotations

import argparse
from pathlib import Path

from document_intelligence.freeze import FreezeManifest, build_manifest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src/document_intelligence/defaults/frozen_contracts_v1.json"
DOC = ROOT / "docs/phase-9/FROZEN_CONTRACTS_V1.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--initialize",
        action="store_true",
        help="write the first stable-major manifest; refuses to overwrite by default",
    )
    args = parser.parse_args()
    manifest = build_manifest()
    rendered = manifest.model_dump_json(indent=2) + "\n"
    if args.initialize:
        if OUT.exists():
            existing = FreezeManifest.model_validate_json(OUT.read_text(encoding="utf-8"))
            if existing.stable_major >= manifest.stable_major:
                raise SystemExit(
                    "refusing to overwrite an existing stable-major freeze manifest"
                )
        OUT.write_text(rendered, encoding="utf-8")
        DOC.parent.mkdir(parents=True, exist_ok=True)
        DOC.write_text(rendered, encoding="utf-8")
    else:
        if not OUT.is_file():
            raise SystemExit("freeze manifest is missing; initialize it explicitly")
        existing = FreezeManifest.model_validate_json(OUT.read_text(encoding="utf-8"))
        if existing != manifest:
            raise SystemExit(
                "live contracts differ from the checked-in freeze; a 1.x release cannot "
                "regenerate the manifest to hide the change"
            )
        if not DOC.is_file() or DOC.read_text(encoding="utf-8") != rendered:
            raise SystemExit("documented freeze manifest differs from the packaged manifest")
    print(manifest.manifest_digest)


if __name__ == "__main__":
    main()
