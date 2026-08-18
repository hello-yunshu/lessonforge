from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

FIXED_ZIP_TIME = (2026, 8, 4, 0, 0, 0)
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024 * 1024
SKIP_NAMES = {".gitkeep"}
SKIP_SUFFIXES = {".lock", ".tmp"}


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def workspace_files(workspace: Path) -> list[Path]:
    if workspace.is_symlink() or not workspace.is_dir():
        raise ValueError("workspace must be a real directory")
    files: list[Path] = []
    for path in workspace.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"workspace contains a symlink: {path}")
        if not path.is_file() or path.name in SKIP_NAMES or path.suffix in SKIP_SUFFIXES:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(workspace).as_posix())


def create_backup(workspace: Path, output: Path) -> dict[str, object]:
    files = workspace_files(workspace)
    records = []
    total = 0
    for path in files:
        data = path.read_bytes()
        total += len(data)
        if len(data) > MAX_MEMBER_BYTES or total > MAX_ARCHIVE_BYTES:
            raise ValueError("workspace backup exceeds configured limits")
        records.append(
            {
                "path": path.relative_to(workspace).as_posix(),
                "size": len(data),
                "sha256": digest_bytes(data),
            }
        )
    manifest = {
        "schema_version": 1,
        "format": "document-intelligence-workspace-backup",
        "files": records,
        "total_bytes": total,
    }
    manifest_bytes = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest["manifest_sha256"] = digest_bytes(manifest_bytes)
    final_manifest = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        info = zipfile.ZipInfo("manifest.json", FIXED_ZIP_TIME)
        info.external_attr = (0o600 & 0xFFFF) << 16
        archive.writestr(info, final_manifest)
        for path in files:
            relative = path.relative_to(workspace).as_posix()
            info = zipfile.ZipInfo(f"data/{relative}", FIXED_ZIP_TIME)
            info.external_attr = (0o600 & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes())
    os.replace(temp, output)
    return manifest


def safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("backup contains an unsafe member path")
    return path


def verify_backup(archive_path: Path) -> dict[str, object]:
    if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("backup archive exceeds size limit")
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise ValueError("backup member set is invalid")
        for info in archive.infolist():
            safe_member(info.filename)
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError("backup member exceeds size limit")
            if info.compress_size and info.file_size / info.compress_size > 200:
                raise ValueError("backup compression ratio exceeds limit")
        manifest = json.loads(archive.read("manifest.json"))
        claimed = manifest.pop("manifest_sha256")
        expected = digest_bytes(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        if claimed != expected:
            raise ValueError("backup manifest integrity check failed")
        expected_names = {f"data/{item['path']}" for item in manifest["files"]}
        if set(names) != {"manifest.json", *expected_names}:
            raise ValueError("backup member list does not match manifest")
        for item in manifest["files"]:
            data = archive.read(f"data/{item['path']}")
            if len(data) != item["size"] or digest_bytes(data) != item["sha256"]:
                raise ValueError("backup member integrity check failed")
        manifest["manifest_sha256"] = claimed
        return manifest


def restore_backup(archive_path: Path, destination: Path) -> dict[str, object]:
    manifest = verify_backup(archive_path)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("restore destination must be empty")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{destination.name}.restore-", dir=destination.parent
    ) as temp_value:
        temp = Path(temp_value)
        with zipfile.ZipFile(archive_path) as archive:
            for item in manifest["files"]:
                relative = safe_member(str(item["path"]))
                target = temp.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(f"data/{item['path']}"))
        if destination.exists():
            destination.rmdir()
        os.replace(temp, destination)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("workspace", type=Path)
    create.add_argument("output", type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("archive", type=Path)
    restore = subparsers.add_parser("restore")
    restore.add_argument("archive", type=Path)
    restore.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        result = create_backup(args.workspace, args.output)
    elif args.command == "verify":
        result = verify_backup(args.archive)
    else:
        result = restore_backup(args.archive, args.destination)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
