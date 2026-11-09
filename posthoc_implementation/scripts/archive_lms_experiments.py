#!/usr/bin/env python3
"""Move legacy LM Studio batches and runs into a recoverable local archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _model_ids(document: dict) -> list[str]:
    if isinstance(document.get("models"), list):
        return [str(value) for value in document["models"]]
    model = document.get("model") or {}
    return [str(model["model_id"])] if model.get("model_id") else []


def _legacy_batch(document: dict) -> bool:
    freeze_id = str(document.get("freeze_id") or "")
    models = _model_ids(document)
    return "local-mac" in freeze_id or bool(models) and all(
        model.startswith("local-") or model == "qwen3-coder" for model in models
    )


def _legacy_manifest(document: dict) -> bool:
    model = document.get("model") or {}
    model_id = str(model.get("model_id") or "")
    base_url = str(model.get("base_url") or "")
    return (
        model_id.startswith("local-")
        or model_id == "qwen3-coder"
        or "localhost:1234" in base_url
    )


def _rewrite_manifest_paths(document: dict, archived_runs: Path) -> None:
    for collection in ("runs", "invalid_attempts"):
        for item in document.get(collection, []):
            run_id = item.get("run_id")
            if run_id and (archived_runs / run_id / "manifest.json").is_file():
                item["manifest_path"] = str(
                    (archived_runs / run_id / "manifest.json").resolve()
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs-root", type=Path, default=PROJECT_ROOT / "experiments" / "runs"
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=PROJECT_ROOT / "experiments" / "run_archive" / "lms-through-v7",
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    runs_root = args.runs_root.resolve()
    archive_root = args.archive_root.resolve()
    batch_paths: list[Path] = []
    batch_documents: dict[Path, dict] = {}
    protected_run_ids: set[str] = set()
    for path in sorted(runs_root.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if _legacy_batch(document):
            batch_paths.append(path)
            batch_documents[path] = document
        else:
            protected_run_ids.update(
                str(item["run_id"])
                for item in document.get("runs", [])
                if item.get("run_id")
            )

    run_dirs: list[Path] = []
    for path in sorted(runs_root.iterdir()):
        manifest_path = path / "manifest.json"
        if not path.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if _legacy_manifest(manifest):
            if path.name in protected_run_ids:
                raise RuntimeError(f"legacy run is referenced by a retained batch: {path.name}")
            run_dirs.append(path)

    print(f"legacy batch summaries: {len(batch_paths)}")
    print(f"legacy run directories: {len(run_dirs)}")
    print(f"archive destination: {archive_root}")
    if not args.execute:
        print("dry run only; pass --execute to move these artifacts")
        return 0
    if archive_root.exists():
        raise RuntimeError(f"archive destination already exists: {archive_root}")

    archived_batches = archive_root / "batches"
    archived_runs = archive_root / "runs"
    archived_batches.mkdir(parents=True)
    archived_runs.mkdir()
    run_moves = []
    for source in run_dirs:
        destination = archived_runs / source.name
        shutil.move(str(source), destination)
        run_moves.append({"run_id": source.name, "from": str(source), "to": str(destination)})

    batch_moves = []
    for source in batch_paths:
        document = batch_documents[source]
        original_sha256 = _sha256(source)
        _rewrite_manifest_paths(document, archived_runs)
        destination = archived_batches / source.name
        destination.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        source.unlink()
        batch_moves.append(
            {
                "filename": source.name,
                "from": str(source),
                "to": str(destination),
                "original_sha256": original_sha256,
                "archived_sha256": _sha256(destination),
            }
        )

    index = {
        "archive_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "operation": "recoverable_move",
        "selection": "LM Studio/local model batches and manifests through local-mac v7",
        "batch_count": len(batch_moves),
        "run_directory_count": len(run_moves),
        "batches": batch_moves,
        "runs": run_moves,
    }
    (archive_root / "archive_index.json").write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8"
    )
    print(f"archived {len(batch_moves)} batches and {len(run_moves)} runs")
    print(f"index: {archive_root / 'archive_index.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
