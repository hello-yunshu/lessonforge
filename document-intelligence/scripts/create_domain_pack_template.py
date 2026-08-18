from __future__ import annotations

import argparse
from pathlib import Path

from document_intelligence.domain_pack_sdk import (
    DomainPackTemplateKind,
    create_domain_pack_scaffold,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target_parent", type=Path)
    parser.add_argument("--id", required=True, dest="pack_id")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument(
        "--template",
        choices=[item.value for item in DomainPackTemplateKind],
        default=DomainPackTemplateKind.CLASSIFICATION.value,
    )
    parser.add_argument("--without-family-profile", action="store_true")
    args = parser.parse_args()
    target = create_domain_pack_scaffold(
        args.target_parent,
        pack_id=args.pack_id,
        version=args.version,
        template=DomainPackTemplateKind(args.template),
        include_family_profile=not args.without_family_profile,
    )
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
