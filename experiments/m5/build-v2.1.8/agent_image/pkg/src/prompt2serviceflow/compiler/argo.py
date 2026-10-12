"""Deterministic Argo projection for one benchmark instance."""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

from prompt2serviceflow.validators.schema_validation import (
    load_document,
    load_schema,
    validate_against_schema,
)


WORKSPACE_MOUNT = "/workspace"
SCRIPT_MOUNT = "/opt/p2sf/scripts"
FIXTURE_MOUNT = "/opt/p2sf/fixtures"
ROOT = Path(__file__).resolve().parents[3]


def kubernetes_name(value: str, *, max_length: int = 63) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.lower().replace("_", "-"))
    normalized = normalized.strip("-")
    if len(normalized) <= max_length:
        return normalized
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]
    prefix = normalized[: max_length - len(digest) - 1].rstrip("-")
    return f"{prefix}-{digest}"


def replace_runtime_tokens(value: str) -> str:
    value = value.replace("{workspace}", WORKSPACE_MOUNT)
    value = value.replace("{fixtures}", FIXTURE_MOUNT)
    return re.sub(
        r"\{([a-z][a-z0-9_-]*)\}",
        lambda match: "{{workflow.parameters." + match.group(1).replace("_", "-") + "}}",
        value,
    )


def load_runtime_manifest(instance_dir: Path) -> dict[str, Any]:
    manifest_path = instance_dir / "runtime" / "manifest.yaml"
    manifest = load_document(manifest_path)
    schema = load_schema(ROOT / "schemas" / "runtime_manifest.schema.json")
    validate_against_schema(manifest, schema)
    return manifest


def _scenario_fixture_root(
    instance_dir: Path,
    manifest: dict[str, Any],
    scenario_name: str | None = None,
) -> tuple[dict[str, Any], Path]:
    scenarios = manifest["scenarios"]
    selected = next(
        (item for item in scenarios if item["name"] == scenario_name),
        scenarios[0] if scenario_name is None else None,
    )
    if selected is None:
        raise ValueError(f"unknown runtime scenario {scenario_name!r}")
    relative = selected.get("fixture_root")
    if relative is None:
        conventional = Path("fixtures") / "scenarios" / selected["name"]
        relative = str(conventional if (instance_dir / conventional).is_dir() else Path("fixtures/inputs"))
    fixture_root = (instance_dir / relative).resolve()
    try:
        fixture_root.relative_to(instance_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"scenario fixture root escapes the instance: {relative!r}") from exc
    if not fixture_root.is_dir():
        raise ValueError(f"scenario fixture root does not exist: {relative!r}")
    return selected, fixture_root


def _text_configmap_data(paths: list[Path]) -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(set(paths))}


def _fixture_configmap_payload(root: Path, paths: list[Path]) -> dict[str, Any]:
    data: dict[str, str] = {}
    binary_data: dict[str, str] = {}
    items: list[dict[str, str]] = []
    for index, path in enumerate(sorted(paths)):
        key = f"fixture-{index:04d}"
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        try:
            data[key] = content.decode("utf-8")
        except UnicodeDecodeError:
            binary_data[key] = base64.b64encode(content).decode("ascii")
        items.append({"key": key, "path": relative})
    payload: dict[str, Any] = {"items": items}
    if data:
        payload["data"] = data
    if binary_data:
        payload["binaryData"] = binary_data
    return payload


def build_resources(instance_dir: Path, *, scenario_name: str | None = None) -> dict[str, Any]:
    manifest = load_runtime_manifest(instance_dir)
    pipeline_id = manifest["pipeline_id"]
    scenario, fixture_root = _scenario_fixture_root(instance_dir, manifest, scenario_name)
    base_workflow_name = kubernetes_name(pipeline_id, max_length=52)
    workflow_name = (
        base_workflow_name
        if scenario_name is None
        else kubernetes_name(f"{pipeline_id}-{scenario['name']}", max_length=52)
    )
    script_files = [instance_dir / "runtime" / task["script"] for task in manifest["tasks"]]
    fixture_files = [path for path in fixture_root.rglob("*") if path.is_file()]
    fixture_payload = _fixture_configmap_payload(fixture_root, fixture_files)
    scripts_configmap_name = f"{workflow_name}-scripts"
    fixtures_configmap_name = f"{workflow_name}-fixtures"

    task_names = {
        task["intent_id"]: kubernetes_name(task["intent_id"]) for task in manifest["tasks"]
    }
    dag_tasks: list[dict[str, Any]] = []
    task_templates: list[dict[str, Any]] = []

    for task in manifest["tasks"]:
        intent_id = task["intent_id"]
        task_name = task_names[intent_id]
        dag_task: dict[str, Any] = {"name": task_name, "template": f"run-{task_name}"}
        if task.get("dependencies"):
            dag_task["depends"] = " && ".join(
                f"{task_names[item]}.Succeeded" for item in task["dependencies"]
            )
        if task.get("depends"):
            depends = task["depends"]
            for source_id, source_name in task_names.items():
                depends = depends.replace(source_id, source_name)
            dag_task["depends"] = depends
        if task.get("when"):
            when = task["when"]
            for source_id, source_name in task_names.items():
                when = when.replace(f"tasks.{source_id}.", f"tasks.{source_name}.")
            dag_task["when"] = when
        dag_tasks.append(dag_task)

        template: dict[str, Any] = {
            "name": f"run-{task_name}",
            "metadata": {
                "annotations": {
                    "prompt2serviceflow/intent-id": intent_id,
                }
            },
            "container": {
                "image": manifest["image"],
                "command": ["python"],
                "args": [
                    f"{SCRIPT_MOUNT}/{Path(task['script']).name}",
                    *[replace_runtime_tokens(item) for item in task["arguments"]],
                ],
                "volumeMounts": [
                    {"name": "scripts", "mountPath": SCRIPT_MOUNT},
                    {"name": "fixtures", "mountPath": FIXTURE_MOUNT},
                    {"name": "workspace", "mountPath": WORKSPACE_MOUNT},
                ],
                "resources": {
                    "requests": {"cpu": "100m", "memory": "128Mi"},
                    "limits": {"cpu": "500m", "memory": "512Mi"},
                },
            },
        }
        if task.get("output_parameters"):
            template["outputs"] = {
                "parameters": [
                    {"name": item["name"], "valueFrom": {"path": item["path"]}}
                    for item in task["output_parameters"]
                ]
            }
        retries = task.get("retries", 0)
        if retries:
            template["retryStrategy"] = {"limit": str(retries), "retryPolicy": "OnError"}
        task_templates.append(template)

    scenario_parameters = scenario.get("parameters", {})
    workflow_arguments = {
        "parameters": [
            {
                "name": item["name"],
                "value": str(scenario_parameters.get(item["name"], item["default"])),
            }
            for item in manifest["workflow_parameters"]
        ]
    }
    workflow_spec: dict[str, Any] = {
        "entrypoint": "pipeline",
        "serviceAccountName": "prompt2serviceflow-runner",
        "arguments": workflow_arguments,
        "podGC": {"strategy": "OnWorkflowCompletion"},
        "volumeClaimTemplates": [
            {
                "metadata": {"name": "workspace"},
                "spec": {
                    "accessModes": ["ReadWriteOnce"],
                    "resources": {"requests": {"storage": "1Gi"}},
                },
            }
        ],
        "volumes": [
            {"name": "scripts", "configMap": {"name": scripts_configmap_name}},
            {
                "name": "fixtures",
                "configMap": {
                    "name": fixtures_configmap_name,
                    "items": fixture_payload["items"],
                },
            },
        ],
        "templates": [
            {"name": "pipeline", "dag": {"tasks": dag_tasks}},
            *task_templates,
        ],
    }
    workflow = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Workflow",
        "metadata": {
            "generateName": f"{workflow_name}-",
            "namespace": "prompt2serviceflow",
            "labels": {
                "prompt2serviceflow/pipeline": workflow_name,
                "prompt2serviceflow/profile": "mock",
                "prompt2serviceflow/scenario": kubernetes_name(scenario["name"]),
            },
        },
        "spec": workflow_spec,
    }

    cronworkflow = None
    if manifest.get("cron"):
        cronworkflow = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "CronWorkflow",
            "metadata": {
                "name": workflow_name,
                "namespace": "prompt2serviceflow",
            },
            "spec": {
                "schedules": [manifest["cron"]["schedule"]],
                "timezone": manifest["cron"]["timezone"],
                "concurrencyPolicy": "Forbid",
                "workflowSpec": workflow_spec,
            },
        }

    install_manifest = [
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": "prompt2serviceflow-runner",
                "namespace": "prompt2serviceflow",
            },
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": scripts_configmap_name,
                "namespace": "prompt2serviceflow",
            },
            "data": _text_configmap_data(script_files),
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": fixtures_configmap_name,
                "namespace": "prompt2serviceflow",
            },
            **({"data": fixture_payload["data"]} if "data" in fixture_payload else {}),
            **(
                {"binaryData": fixture_payload["binaryData"]}
                if "binaryData" in fixture_payload
                else {}
            ),
        },
    ]
    workflow_bundle = [*install_manifest, workflow]
    cronworkflow_bundle = [*install_manifest, cronworkflow] if cronworkflow else None
    return {
        "scenario": scenario["name"],
        "workflow": workflow,
        "cronworkflow": cronworkflow,
        "install_manifest": install_manifest,
        "workflow_bundle": workflow_bundle,
        "cronworkflow_bundle": cronworkflow_bundle,
    }


def write_resources(instance_dir: Path) -> dict[str, Path]:
    resources = build_resources(instance_dir)
    argo_dir = instance_dir / "argo"
    argo_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}

    workflow_path = argo_dir / "workflow.yaml"
    workflow_path.write_text(
        yaml.safe_dump(resources["workflow"], sort_keys=False, width=100),
        encoding="utf-8",
    )
    outputs["workflow"] = workflow_path

    install_path = argo_dir / "install_manifest.yaml"
    install_path.write_text(
        yaml.safe_dump_all(resources["install_manifest"], sort_keys=False, width=100),
        encoding="utf-8",
    )
    outputs["install_manifest"] = install_path

    workflow_bundle_path = argo_dir / "workflow_bundle.yaml"
    workflow_bundle_path.write_text(
        yaml.safe_dump_all(resources["workflow_bundle"], sort_keys=False, width=100),
        encoding="utf-8",
    )
    outputs["workflow_bundle"] = workflow_bundle_path

    if resources["cronworkflow"]:
        cron_path = argo_dir / "cronworkflow.yaml"
        cron_path.write_text(
            yaml.safe_dump(resources["cronworkflow"], sort_keys=False, width=100),
            encoding="utf-8",
        )
        outputs["cronworkflow"] = cron_path

        cronworkflow_bundle_path = argo_dir / "cronworkflow_bundle.yaml"
        cronworkflow_bundle_path.write_text(
            yaml.safe_dump_all(resources["cronworkflow_bundle"], sort_keys=False, width=100),
            encoding="utf-8",
        )
        outputs["cronworkflow_bundle"] = cronworkflow_bundle_path
    else:
        for path in (argo_dir / "cronworkflow.yaml", argo_dir / "cronworkflow_bundle.yaml"):
            path.unlink(missing_ok=True)

    manifest = load_runtime_manifest(instance_dir)
    for scenario in manifest["scenarios"]:
        scenario_resources = build_resources(instance_dir, scenario_name=scenario["name"])
        scenario_dir = argo_dir / "scenarios" / scenario["name"]
        scenario_dir.mkdir(parents=True, exist_ok=True)
        (scenario_dir / "workflow.yaml").write_text(
            yaml.safe_dump(scenario_resources["workflow"], sort_keys=False, width=100),
            encoding="utf-8",
        )
        (scenario_dir / "install_manifest.yaml").write_text(
            yaml.safe_dump_all(
                scenario_resources["install_manifest"], sort_keys=False, width=100
            ),
            encoding="utf-8",
        )
        (scenario_dir / "workflow_bundle.yaml").write_text(
            yaml.safe_dump_all(
                scenario_resources["workflow_bundle"], sort_keys=False, width=100
            ),
            encoding="utf-8",
        )
        if scenario_resources["cronworkflow"]:
            (scenario_dir / "cronworkflow.yaml").write_text(
                yaml.safe_dump(
                    scenario_resources["cronworkflow"], sort_keys=False, width=100
                ),
                encoding="utf-8",
            )
            (scenario_dir / "cronworkflow_bundle.yaml").write_text(
                yaml.safe_dump_all(
                    scenario_resources["cronworkflow_bundle"], sort_keys=False, width=100
                ),
                encoding="utf-8",
            )
        else:
            for path in (
                scenario_dir / "cronworkflow.yaml",
                scenario_dir / "cronworkflow_bundle.yaml",
            ):
                path.unlink(missing_ok=True)
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance_dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for kind, path in write_resources(args.instance_dir.resolve()).items():
        print(f"generated {kind}: {path}")


if __name__ == "__main__":
    main()
