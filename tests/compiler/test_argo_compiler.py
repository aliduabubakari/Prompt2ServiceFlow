from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from prompt2serviceflow.compiler.argo import build_resources, write_resources


ROOT = Path(__file__).resolve().parents[2]
INSTANCES = ROOT / "benchmark" / "instances" / "main"
EXTENSION_INSTANCES = ROOT / "benchmark" / "instances" / "extension"


@pytest.mark.parametrize(
    ("pipeline_id", "task_count", "has_cron"),
    [
        ("airvisual_pipeline_lat_long_v1", 3, False),
        ("data_quality_gate", 6, True),
    ],
)
def test_pilot_argo_projection_is_deterministic(
    pipeline_id: str, task_count: int, has_cron: bool
) -> None:
    instance_dir = INSTANCES / pipeline_id

    first = build_resources(instance_dir)
    second = build_resources(instance_dir)

    assert first == second
    assert len(first["workflow"]["spec"]["templates"][0]["dag"]["tasks"]) == task_count
    assert (first["cronworkflow"] is not None) is has_cron
    assert first["workflow_bundle"] == [*first["install_manifest"], first["workflow"]]
    assert (first["cronworkflow_bundle"] is not None) is has_cron
    if has_cron:
        assert first["cronworkflow"]["spec"]["schedules"] == [
            yaml.safe_load((instance_dir / "runtime" / "manifest.yaml").read_text(encoding="utf-8"))["cron"][
                "schedule"
            ]
        ]
        assert first["cronworkflow_bundle"] == [
            *first["install_manifest"],
            first["cronworkflow"],
        ]


def test_data_quality_gate_uses_enhanced_dependencies_consistently() -> None:
    resources = build_resources(INSTANCES / "data_quality_gate")
    tasks = resources["workflow"]["spec"]["templates"][0]["dag"]["tasks"]

    assert all("dependencies" not in task for task in tasks)
    cleanup = next(task for task in tasks if task["name"] == "cleanup-temporary-resources")
    assert cleanup["depends"] == (
        "(load-production-data.Succeeded || notify-data-stewards.Succeeded)"
    )


def test_writes_separate_deployable_workflow_and_cronworkflow_bundles(tmp_path: Path) -> None:
    instance_dir = tmp_path / "data_quality_gate"
    shutil.copytree(INSTANCES / "data_quality_gate", instance_dir)

    outputs = write_resources(instance_dir)

    workflow_bundle = list(
        yaml.safe_load_all(outputs["workflow_bundle"].read_text(encoding="utf-8"))
    )
    cronworkflow_bundle = list(
        yaml.safe_load_all(outputs["cronworkflow_bundle"].read_text(encoding="utf-8"))
    )

    assert [document["kind"] for document in workflow_bundle] == [
        "ServiceAccount",
        "ConfigMap",
        "ConfigMap",
        "Workflow",
    ]
    assert [document["kind"] for document in cronworkflow_bundle] == [
        "ServiceAccount",
        "ConfigMap",
        "ConfigMap",
        "CronWorkflow",
    ]


def test_scenario_projection_preserves_binary_fixture_paths() -> None:
    resources = build_resources(
        EXTENSION_INSTANCES / "crop_disease_image_triage", scenario_name="nominal"
    )
    fixture_configmap = resources["install_manifest"][2]
    fixture_volume = resources["workflow"]["spec"]["volumes"][1]["configMap"]

    assert fixture_configmap["binaryData"]
    assert "sample_image.png" in {item["path"] for item in fixture_volume["items"]}
    assert resources["workflow"]["metadata"]["labels"]["prompt2serviceflow/scenario"] == "nominal"


def test_distinct_scenarios_compile_distinct_fixture_configmaps() -> None:
    instance = EXTENSION_INSTANCES / "clickstream_session_window_batch"

    nominal = build_resources(instance, scenario_name="nominal")["install_manifest"][2]
    boundary = build_resources(instance, scenario_name="boundary")["install_manifest"][2]

    assert nominal != boundary
