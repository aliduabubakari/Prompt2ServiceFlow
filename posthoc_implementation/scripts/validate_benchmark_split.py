#!/usr/bin/env python3
"""Compile and validate every available instance in a benchmark split."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prompt2serviceflow.compiler.argo import write_resources  # noqa: E402
from prompt2serviceflow.validators.instance_validation import validate_instance  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split", choices=["main", "validation", "extension", "all"])
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument(
        "--pipeline",
        action="append",
        default=[],
        help="Restrict validation to one or more instance directory names.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    instance_roots = (
        [ROOT / "benchmark" / "instances" / name for name in ("main", "validation", "extension")]
        if args.split == "all"
        else [ROOT / "benchmark" / "instances" / args.split]
    )
    selected = set(args.pipeline)
    available = {
        path.name for instances_root in instance_roots for path in instances_root.iterdir() if path.is_dir()
    }
    unknown = sorted(selected - available)
    if unknown:
        raise ValueError(f"Unknown {args.split} pipeline(s): {unknown}")
    instances = sorted(
        path
        for instances_root in instance_roots
        for path in instances_root.iterdir()
        if path.is_dir() and (not selected or path.name in selected)
    )
    failures: list[tuple[str, list[str]]] = []

    for index, instance_dir in enumerate(instances, start=1):
        if args.compile:
            write_resources(instance_dir)
        report = validate_instance(instance_dir, write_report=not args.no_write)
        status = report["overall_status"]
        print(
            f"[{index}/{len(instances)}] {instance_dir.parent.name}:{instance_dir.name} {status}",
            flush=True,
        )
        if status == "fail":
            errors = [
                f"{gate['gate']}: {error}"
                for gate in report["gates"]
                for error in gate["errors"]
            ]
            failures.append((instance_dir.name, errors))

    print(
        f"summary: split={args.split} total={len(instances)} "
        f"passed={len(instances) - len(failures)} failed={len(failures)}",
        flush=True,
    )
    for pipeline_id, errors in failures:
        print(f"failed {args.split}:{pipeline_id}")
        for error in errors:
            print(f"  - {error}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
