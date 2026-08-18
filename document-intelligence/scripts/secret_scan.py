from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "phase-12" / "secret_scan.json"
PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "aws-access-key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "generic-secret-assignment": re.compile(
        r"(?i)(?:password|secret|api[_-]?key)\s*[:=]\s*['\"][^'\"]{12,}['\"]"
    ),
}
SKIP_PARTS = {".git", "dist", "build", "__pycache__", ".pytest_cache"}


def main() -> None:
    findings: list[dict[str, object]] = []
    checked = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() in {".zip", ".whl", ".png", ".jpg", ".jpeg", ".pdf", ".npz"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        checked += 1
        for name, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    {"kind": name, "path": path.relative_to(ROOT).as_posix(), "line": line}
                )
    payload = {"phase": 12, "passed": not findings, "checked_files": checked, "findings": findings}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
