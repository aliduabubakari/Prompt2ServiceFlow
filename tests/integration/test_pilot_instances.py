from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from prompt2serviceflow.validators.instance_validation import (
    _runtime_graph_errors,
    validate_instance,
)


ROOT = Path(__file__).resolve().parents[2]
INSTANCES = ROOT / "benchmark" / "instances" / "main"


@pytest.mark.parametrize(
    "pipeline_id",
    [
        "airvisual_pipeline_lat_long_v1",
        "data_quality_gate",
    ],
)
def test_pilot_instance_passes_g0_through_g6(pipeline_id: str) -> None:
    report = validate_instance(INSTANCES / pipeline_id, write_report=False)

    assert report["overall_status"] == "pass"
    assert [gate["gate"] for gate in report["gates"]] == [f"G{index}" for index in range(7)]
    assert all(gate["status"] == "pass" for gate in report["gates"])


def test_data_quality_gate_exercises_both_routes() -> None:
    report = validate_instance(INSTANCES / "data_quality_gate", write_report=False)
    scenarios = {item["scenario"]: item for item in report["scenario_results"]}
    g5 = next(gate for gate in report["gates"] if gate["gate"] == "G5")

    assert scenarios["high_quality_production"]["skipped_tasks"] == [
        "quarantine_customer_data",
        "notify_data_stewards",
    ]
    assert scenarios["low_quality_quarantine"]["skipped_tasks"] == [
        "load_production_data"
    ]
    assert all(item["within_limit"] for item in g5["details"]["configmap_payloads"])


def test_all_main_instances_pass_g0_through_g6() -> None:
    instances = sorted(path for path in INSTANCES.iterdir() if path.is_dir())

    assert len(instances) == 40
    failures = {}
    for instance in instances:
        report = validate_instance(instance, write_report=False)
        if report["overall_status"] != "pass":
            failures[instance.name] = {
                gate["gate"]: gate["errors"]
                for gate in report["gates"]
                if gate["status"] == "fail"
            }

    assert failures == {}


def test_all_110_packages_have_aligned_runtime_scenarios_and_current_reports() -> None:
    instances = sorted(
        path
        for split in ("main", "validation", "extension")
        for path in (ROOT / "benchmark" / "instances" / split).iterdir()
        if path.is_dir()
    )

    assert len(instances) == 110
    for instance in instances:
        manifest = yaml.safe_load((instance / "runtime" / "manifest.yaml").read_text())
        serviceflow = yaml.safe_load((instance / "gold" / "serviceflow.yaml").read_text())
        assertions = yaml.safe_load((instance / "gold" / "assertions.yaml").read_text())
        report = json.loads((instance / "validation" / "report.json").read_text())

        assert _runtime_graph_errors(serviceflow, manifest, instance) == []
        assert {item["name"] for item in manifest["scenarios"]} == {
            item["scenario"] for item in assertions["scenarios"]
        }
        assert all((instance / item["fixture_root"]).is_dir() for item in manifest["scenarios"])
        assert report["overall_status"] == "pass"
        assert [gate["gate"] for gate in report["gates"]] == [f"G{i}" for i in range(7)]
