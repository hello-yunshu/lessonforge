from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PHASE = 12
DISPLAY_VERSION = "1.0.3-rc.1"
ARCHIVE_NAME = f"document-intelligence_phase{PHASE}_{DISPLAY_VERSION}.zip"
FIXED_ZIP_TIME = (2026, 8, 4, 0, 0, 0)
EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    ".coverage",
    "htmlcov",
    "build",
    "dist",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def included_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in relative.parts):
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            continue
        if relative.parts and relative.parts[0] == "var" and path.name != ".gitkeep":
            continue
        if relative == Path("SHA256SUMS"):
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


def write_source_manifest(files: list[Path]) -> None:
    lines = [f"{sha256(path)}  {path.relative_to(ROOT).as_posix()}" for path in files]
    (ROOT / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def zip_entry(archive: zipfile.ZipFile, source: Path, arcname: str) -> None:
    info = zipfile.ZipInfo(arcname, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o644 & 0xFFFF) << 16
    archive.writestr(info, source.read_bytes())


def build_source_zip(files: list[Path]) -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    target = DIST / ARCHIVE_NAME
    target.unlink(missing_ok=True)
    all_files = sorted(
        [*files, ROOT / "SHA256SUMS"],
        key=lambda item: item.relative_to(ROOT).as_posix(),
    )
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in all_files:
            relative = path.relative_to(ROOT).as_posix()
            zip_entry(archive, path, f"document-intelligence/{relative}")
    with zipfile.ZipFile(target) as archive:
        bad = archive.testzip()
        if bad is not None:
            raise RuntimeError(f"source archive integrity failed at {bad}")
    return target


def run(command: list[str], *, cwd: Path) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        env={**os.environ, "SOURCE_DATE_EPOCH": "1785801600"},
    )
    if completed.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{completed.stdout}")


def normalize_wheel(source: Path, target: Path) -> None:
    with zipfile.ZipFile(source) as incoming, zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as outgoing:
        for name in sorted(incoming.namelist()):
            if name.endswith("/"):
                continue
            info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 & 0xFFFF) << 16
            outgoing.writestr(info, incoming.read(name))


def build_reproducible_wheel() -> tuple[Path, str]:
    DIST.mkdir(parents=True, exist_ok=True)
    normalized: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="di-rc-wheel-") as temp_value:
        temp = Path(temp_value)
        for index in range(2):
            wheel_dir = temp / f"wheel-{index}"
            wheel_dir.mkdir()
            run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    ".",
                    "--no-deps",
                    "--no-build-isolation",
                    "--wheel-dir",
                    str(wheel_dir),
                ],
                cwd=ROOT,
            )
            wheels = list(wheel_dir.glob("document_intelligence-*.whl"))
            if len(wheels) != 1:
                raise RuntimeError(f"expected one wheel, found {wheels}")
            normalized_path = temp / f"normalized-{index}.whl"
            normalize_wheel(wheels[0], normalized_path)
            normalized.append(normalized_path)
        digests = [sha256(path) for path in normalized]
        if digests[0] != digests[1]:
            raise RuntimeError("normalized wheel build is not reproducible")
        wheel_name = list((temp / "wheel-0").glob("document_intelligence-*.whl"))[0].name
        target = DIST / wheel_name
        shutil.copyfile(normalized[0], target)
        return target, digests[0]


def main() -> None:
    wheel, wheel_digest = build_reproducible_wheel()
    report_path = ROOT / "docs" / "phase-12" / "release_build.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "phase": PHASE,
        "version": DISPLAY_VERSION,
        "source_archive": ARCHIVE_NAME,
        "source_files": 0,
        "wheel": wheel.name,
        "wheel_sha256": wheel_digest,
        "wheel_reproducible_two_builds": True,
        "source_zip_fixed_timestamp": "2026-08-04T00:00:00Z",
        "production_qualification_claimed": False,
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    files = included_files()
    report["source_files"] = len(files) + 1
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    files = included_files()
    write_source_manifest(files)
    files = included_files()
    source_zip = build_source_zip(files)
    source_digest = sha256(source_zip)
    checksum_path = source_zip.with_suffix(source_zip.suffix + ".sha256")
    checksum_path.write_text(
        f"{source_digest}  {source_zip.name}\n", encoding="utf-8"
    )
    output = {**report, "source_archive_sha256": source_digest}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
