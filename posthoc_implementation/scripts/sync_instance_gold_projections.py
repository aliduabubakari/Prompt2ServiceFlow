#!/usr/bin/env python3
"""Synchronize compact gold projections from authoritative ServiceFlowIR files."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_yaml(path: Path, document: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False, width=100), encoding="utf-8")


def port_projection(bindings: list[dict[str, Any]]) -> dict[str, str | list[str]]:
    projected: dict[str, str | list[str]] = {}
    for binding in bindings:
        port = binding["port"]
        artifact_id = binding["artifact_id"]
        current = projected.get(port)
        if current is None:
            projected[port] = artifact_id
        elif isinstance(current, list):
            current.append(artifact_id)
        else:
            projected[port] = [current, artifact_id]
    return projected


def projections(instance_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    serviceflow = load_yaml(instance_dir / "gold" / "serviceflow.yaml")
    benchmark_id = serviceflow["source"]["benchmark_id"]
    bindings = {
        "binding_gold_version": "0.1.0",
        "benchmark_id": benchmark_id,
        "bindings": [
            {
                "intent_id": item["intent_id"],
                "service_id": item["service_id"],
                "service_version": item["service_version"],
            }
            for item in serviceflow["bindings"]
        ],
    }
    mappings = {
        "artifact_mapping_version": "0.1.0",
        "benchmark_id": benchmark_id,
        "mappings": [
            {
                "intent_id": item["intent_id"],
                "inputs": port_projection(item["input_bindings"]),
                "outputs": port_projection(item["output_bindings"]),
            }
            for item in serviceflow["bindings"]
        ],
    }
    return bindings, mappings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="main")
    parser.add_argument("--pipeline", action="append", default=[])
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = ROOT / "benchmark" / "instances" / args.split
    selected = set(args.pipeline)
    drifted = []
    for instance_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        if selected and instance_dir.name not in selected:
            continue
        bindings, mappings = projections(instance_dir)
        binding_path = instance_dir / "gold" / "bindings.yaml"
        mapping_path = instance_dir / "gold" / "artifact_mappings.yaml"
        if load_yaml(binding_path) == bindings and load_yaml(mapping_path) == mappings:
            continue
        drifted.append(instance_dir.name)
        if not args.check:
            write_yaml(binding_path, bindings)
            write_yaml(mapping_path, mappings)
            print(f"synchronized gold projections: {args.split}:{instance_dir.name}")
    if args.check and drifted:
        for pipeline_id in drifted:
            print(f"gold projection drift: {args.split}:{pipeline_id}")
        raise SystemExit(1)
    print(f"gold projection synchronization complete: drifted={len(drifted)}")


if __name__ == "__main__":
    main()
