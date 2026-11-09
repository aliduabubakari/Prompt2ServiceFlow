#!/usr/bin/env python3
"""Verify and extract the locally downloaded profile-38.1 archive; no execution."""
import argparse
import hashlib
import json
from pathlib import Path
from fetch_replication_evidence import extract


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    pin = json.loads((root / "replication/POSTHOC_MANIFEST.json").read_text())
    with a.archive.open("rb") as handle:
        actual = hashlib.file_digest(handle, "sha256").hexdigest()
    if actual != pin["archive_sha256"]:
        raise ValueError("Post-hoc archive does not match pinned release")
    extract(a.archive, a.output.resolve())
    print("Verified and extracted post-hoc evidence to " + str(a.output.resolve()))


if __name__ == "__main__":
    main()
