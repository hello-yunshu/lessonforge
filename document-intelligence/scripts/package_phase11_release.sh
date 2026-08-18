#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${OUT_DIR:-$ROOT/dist}"
NAME="document-intelligence_phase11_1.0.2"
mkdir -p "$OUT_DIR"
cd "$ROOT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

python scripts/generate_fixtures.py
for phase in $(seq 1 11); do
  python "scripts/run_phase${phase}_benchmark.py"
done
python scripts/generate_dependency_report.py
python scripts/export_schemas.py
python scripts/generate_freeze_manifest.py
for phase in $(seq 1 11); do
  python "scripts/verify_phase${phase}.py"
done
python scripts/verify_distribution.py
python scripts/static_sanity.py
python -m compileall -q src tests scripts
python -m pytest --cov=document_intelligence --cov-branch --cov-report=term -q
python -m coverage json -o docs/phase-11/coverage.json
python scripts/generate_source_manifest.py

rm -f "$OUT_DIR/$NAME.zip" "$OUT_DIR/$NAME.zip.sha256"
OUT_DIR="$OUT_DIR" python - <<'PY'
from pathlib import Path
import os
import zipfile

root = Path.cwd()
out = Path(os.environ["OUT_DIR"]) / "document-intelligence_phase11_1.0.2.zip"
excluded = {
    ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__",
    "dist", ".coverage", "htmlcov", "build",
}
runtime_namespaces = {
    "runs", "raw", "sources", "assets", "standard", "structures",
    "domain-packs", "domain-results", "domain-reviews", "family-detections",
    "rill-shadow", "rill-assist", "mlops", "production-qualification",
    "qualification-campaigns",
}
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in excluded for part in relative.parts):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        if any(part.endswith(".egg-info") for part in relative.parts):
            continue
        if len(relative.parts) >= 2 and relative.parts[0] == "var":
            if relative.parts[1] in runtime_namespaces and path.name != ".gitkeep":
                continue
        archive.write(path, Path("document-intelligence") / relative)
print(out)
PY
(
  cd "$OUT_DIR"
  sha256sum "$NAME.zip" > "$NAME.zip.sha256"
)
unzip -t "$OUT_DIR/$NAME.zip" >/dev/null

TEMP_DIR="$(mktemp -d -t di-phase11-release-XXXXXX)"
trap 'rm -rf "$TEMP_DIR"' EXIT
unzip -q "$OUT_DIR/$NAME.zip" -d "$TEMP_DIR"
EXTRACTED="$TEMP_DIR/document-intelligence"
(
    cd "$EXTRACTED"
    sha256sum -c SHA256SUMS >/dev/null
    export PYTHONPATH="$EXTRACTED/src"
    python -m compileall -q src tests scripts
    python -m pytest -q
    python scripts/verify_phase9.py >/dev/null
    python scripts/verify_phase10.py >/dev/null
    python scripts/verify_phase11.py >/dev/null
    python scripts/static_sanity.py >/dev/null
    python -m document_intelligence.cli freeze-verify >/dev/null
    python -m document_intelligence.cli production-inspect >/dev/null
    python -m document_intelligence.cli campaign-inspect >/dev/null
    python - <<'PY'
from document_intelligence import __version__
from document_intelligence.config import Settings
from document_intelligence.freeze import FreezeService
from document_intelligence.production import BOUNDED_AUTO_ENABLED
from document_intelligence.services import (
    build_production_qualification_service,
    build_qualification_campaign_service,
)

assert __version__ == "1.0.2"
assert FreezeService().verify().compatible is True
assert BOUNDED_AUTO_ENABLED is False
settings = Settings()
production = build_production_qualification_service(settings)
assert production.inspect()["qualifiedReportCount"] == 0
campaign = build_qualification_campaign_service(
    settings, production_service=production
)
assert campaign.inspect()["campaignCount"] == 0
assert campaign.inspect()["automaticReleaseAuthorized"] is False
assert campaign.inspect()["boundedAuto"] is False
print(__version__)
PY
)
printf 'verified release: %s\n' "$OUT_DIR/$NAME.zip"
