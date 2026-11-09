#!/usr/bin/env python3
"""Download/verify the pinned original archive and extract to a new directory.

This is read-only access to Zenodo. It does not publish, run models, or execute
generated code. The original archive does not contain the revised post-hoc profile.
"""
import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath


def extract(archive: Path, output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Evidence destination must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or not member.isfile():
                raise ValueError(f"Unsupported archive member: {member.name}")
            target = output.joinpath(*name.parts)
            if not target.resolve().is_relative_to(output.resolve()):
                raise ValueError("Archive path escapes evidence directory")
            if target.exists():
                raise ValueError(f"Duplicate archive member: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(member) as source, target.open("wb") as dest:
                shutil.copyfileobj(source, dest)
            target.chmod(member.mode & 0o777)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use an already downloaded archive")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    record = json.loads((root / "replication/ARCHIVE_MANIFEST.json").read_text())
    with tempfile.TemporaryDirectory() as directory:
        archive = args.archive or Path(directory) / record["filename"]
        if args.archive is None:
            request = urllib.request.Request(record["url"], headers={"User-Agent": "Prompt2ServiceFlow-replication"})
            with urllib.request.urlopen(request, timeout=120) as source, archive.open("wb") as dest:
                shutil.copyfileobj(source, dest)
        with archive.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != record["sha256"]:
            raise ValueError("Archive SHA-256 does not match the pinned release")
        extract(archive, args.output.resolve())
        print(f"Verified and extracted original evidence to {args.output.resolve()}")


if __name__ == "__main__":
    main()
