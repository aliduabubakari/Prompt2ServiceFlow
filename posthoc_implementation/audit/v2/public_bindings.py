"""Public fixture availability contract; no private semantic mapping guesses."""
from __future__ import annotations

import hashlib
from pathlib import Path

import service_executor_v3 as base
import retention_adapter

CONTRACT_VERSION = "2.0.0"


def build(workspace: Path, scenarios: list[dict]) -> dict:
    available = []
    for scenario in scenarios:
        root = base.inside(workspace, scenario["fixture_root"])
        files = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Public fixture escapes scenario root")
            files.append({"fixture_ref": path.relative_to(workspace).as_posix(),
                          "active_relative_path": path.relative_to(root).as_posix(),
                          "bytes": path.stat().st_size,
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        available.append({"name": scenario["name"], "fixture_root": scenario["fixture_root"], "files": files})
    return {"contract_version": CONTRACT_VERSION, "scenarios": available,
            "input_rule": "Explicit fixture_ref only; no inferred artifact-to-file mapping",
            "legacy_fixture_rule": "fixtures/inputs/<path> or fixtures/scenarios/<name>/<path> resolves <path> under each active scenario root",
            "logical_time": "Must be explicitly supplied when required; no wall-clock fallback",
            "private_expected_outputs_included": False}


def validate(spec: dict, manifest: dict) -> list[dict]:
    checks = []
    for port, binding in spec["inputs"].items():
        reference = binding.get("fixture_ref")
        if not reference:
            raise ValueError("Required public input binding is absent; no guessing allowed")
        relative = retention_adapter.fixture_relative(reference).as_posix()
        if relative != binding["relative"]:
            raise ValueError("Derived input path disagrees with explicit fixture binding")
        for scenario in manifest["scenarios"]:
            matches = [f for f in scenario["files"] if f["active_relative_path"] == relative]
            if len(matches) != 1:
                raise ValueError(f"Bound input unavailable in public scenario {scenario['name']}: {reference}")
            checks.append({"port": port, "scenario": scenario["name"], "declared_fixture_ref": reference,
                           "resolved_fixture_ref": matches[0]["fixture_ref"], "sha256": matches[0]["sha256"]})
    return checks
