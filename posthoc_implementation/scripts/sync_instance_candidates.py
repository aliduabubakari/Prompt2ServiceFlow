#!/usr/bin/env python3
"""Synchronize instance candidate sets with reviewed catalogue relationships."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def snake_identifier(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return normalized if normalized and normalized[0].isalpha() else f"id_{normalized}"


def candidate_set_id(benchmark_id: str, service_id: str) -> str:
    return f"{snake_identifier(benchmark_id)}_{snake_identifier(service_id)}_candidates"


def load_manifest_rows() -> dict[str, dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in (ROOT / "benchmark" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {row["description_path"]: row for row in rows}


def load_review_relationships(
    catalog_version: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[tuple[str, dict[str, Any]]]]]:
    path = (
        ROOT
        / "benchmark"
        / "catalog"
        / "review"
        / catalog_version
        / "candidate_relationships.private.json"
    )
    review = json.loads(path.read_text(encoding="utf-8"))
    by_pipeline = {item["pipeline_id"]: item for item in review["pipelines"]}
    by_service: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for pipeline in review["pipelines"]:
        for candidate_set in pipeline["candidate_sets"]:
            by_service.setdefault(candidate_set["required_service_id"], []).append(
                (pipeline["pipeline_id"], candidate_set)
            )
    for templates in by_service.values():
        templates.sort(key=lambda item: (item[0], item[1]["candidate_set_id"]))
    return by_pipeline, by_service


def choose_template(
    pipeline_id: str,
    service_id: str,
    by_pipeline: dict[str, dict[str, Any]],
    by_service: dict[str, list[tuple[str, dict[str, Any]]]],
) -> dict[str, Any]:
    exact = [
        item
        for item in by_pipeline[pipeline_id]["candidate_sets"]
        if item["required_service_id"] == service_id
    ]
    if exact:
        return exact[0]
    templates = by_service.get(service_id, [])
    if not templates:
        raise ValueError(f"No reviewed candidate template exists for service {service_id!r}")
    return templates[0][1]


def expected_documents(
    instance_dir: Path,
    manifest_rows: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    serviceflow = load_yaml(instance_dir / "gold" / "serviceflow.yaml")
    source = serviceflow["source"]
    row = manifest_rows[source["description_path"]]
    catalog_version = serviceflow["catalog_snapshot"]["version"]
    by_pipeline, by_service = load_review_relationships(catalog_version)
    pipeline_id = row["pipeline_id"]
    if pipeline_id not in by_pipeline:
        raise ValueError(f"No reviewed candidate relationships exist for {pipeline_id!r}")

    intents = {item["intent_id"]: item for item in serviceflow["service_intents"]}
    services: dict[str, list[str]] = {}
    for binding in serviceflow["bindings"]:
        service_id = binding["service_id"]
        refs = services.setdefault(service_id, [])
        for ref in intents[binding["intent_id"]]["source_step_refs"]:
            if ref not in refs:
                refs.append(ref)

    public_sets = []
    private_sets = []
    for service_id, source_step_refs in services.items():
        template = choose_template(pipeline_id, service_id, by_pipeline, by_service)
        candidates = template["candidates"]
        set_id = candidate_set_id(row["benchmark_id"], service_id)
        public_sets.append(
            {
                "candidate_set_id": set_id,
                "source_step_refs": source_step_refs,
                "service_ids": [item["service_id"] for item in candidates],
            }
        )
        private_sets.append(
            {
                "candidate_set_id": set_id,
                "required_service_id": service_id,
                "labels": {item["service_id"]: item["label"] for item in candidates},
            }
        )

    public = {
        "candidate_set_version": "0.1.0",
        "benchmark_id": row["benchmark_id"],
        "catalog_snapshot": {
            "catalog_id": serviceflow["catalog_snapshot"]["catalog_id"],
            "version": catalog_version,
        },
        "candidate_sets": public_sets,
    }
    private = {
        "candidate_label_version": "0.1.0",
        "benchmark_id": row["benchmark_id"],
        "candidate_sets": private_sets,
    }
    return public, private


def write_yaml(path: Path, document: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(document, sort_keys=False, width=100),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="main")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report drift without changing files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_rows = load_manifest_rows()
    instances_root = ROOT / "benchmark" / "instances" / args.split
    drifted = []
    for instance_dir in sorted(path for path in instances_root.iterdir() if path.is_dir()):
        public, private = expected_documents(instance_dir, manifest_rows)
        public_path = instance_dir / "candidates" / "candidate_sets.yaml"
        private_path = instance_dir / "gold" / "candidate_labels.yaml"
        if load_yaml(public_path) == public and load_yaml(private_path) == private:
            continue
        drifted.append(instance_dir.name)
        if not args.check:
            write_yaml(public_path, public)
            write_yaml(private_path, private)
            print(f"synchronized candidates: {args.split}:{instance_dir.name}")

    if args.check and drifted:
        for pipeline_id in drifted:
            print(f"candidate drift: {args.split}:{pipeline_id}")
        raise SystemExit(1)
    print(f"candidate synchronization complete: split={args.split} drifted={len(drifted)}")


if __name__ == "__main__":
    main()
