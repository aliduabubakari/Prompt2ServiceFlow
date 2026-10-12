#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
from pathlib import Path

TASK = 'notify_model_team'
parser = argparse.ArgumentParser()
parser.add_argument("--workspace", required=True)
parser.add_argument("--fixture")
args, _ = parser.parse_known_args()
root = Path(args.workspace)
artifact_dir = root / "artifacts"
artifact_dir.mkdir(parents=True, exist_ok=True)

def describe_file(path):
    content = path.read_bytes()
    item = {
        "name": path.name,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "record_count": 0,
    }
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            item["record_count"] = sum(1 for _ in csv.DictReader(handle))
    elif suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        item["record_count"] = len(value) if isinstance(value, (list, dict)) else 1
    elif suffix in {".jsonl", ".ndjson"}:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        item["record_count"] = len(rows)
    elif suffix in {".txt", ".sql", ".conf", ".yaml", ".yml", ".geojson"}:
        text = path.read_text(encoding="utf-8")
        item["record_count"] = len([line for line in text.splitlines() if line.strip()])
    elif suffix == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise ValueError(f"invalid PDF fixture: {path}")
        item["record_count"] = 1
    elif suffix == ".png":
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError(f"invalid PNG fixture: {path}")
        item["record_count"] = 1
    else:
        item["record_count"] = 1
    return item

fixture_path = Path(args.fixture) if args.fixture else None
if fixture_path is None or not fixture_path.is_file():
    raise FileNotFoundError(f"fixture manifest is required for {TASK}: {fixture_path}")
fixture_manifest = json.loads(fixture_path.read_text(encoding="utf-8"))
fixture_files = [
    describe_file(path)
    for path in sorted(fixture_path.parent.rglob("*"))
    if path.is_file() and path != fixture_path
]
fixture_summary = {
    "manifest": fixture_manifest,
    "file_count": len(fixture_files),
    "record_count": sum(item["record_count"] for item in fixture_files),
    "files": fixture_files,
}

upstream = []
for path in sorted(artifact_dir.glob("*.json")):
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        continue
    upstream.append({"artifact": path.stem, "producer": document.get("task")})

def payload(name):
    return {
        "success": True,
        "errors": [],
        "task": TASK,
        "artifact": name,
        "fixture": fixture_summary,
        "upstream_artifact_count": len(upstream),
        "upstream_artifacts": upstream,
    }

def write(name, value):
    (artifact_dir / f"{name}.json").write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

write('model_team_notification_status', payload('model_team_notification_status'))
