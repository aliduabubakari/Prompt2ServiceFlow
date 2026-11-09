"""Reduced, honest assessment for direct-Argo methods (M0-M2).

These methods emit Argo YAML rather than the ServiceFlowIR submission
package, so catalog grounding (G2) applies through fail-closed extraction of
service references, while contract/policy/runtime gates remain explicitly not
applicable. YAML-level structure and offline Argo lint are scored on the
artifact itself.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

import yaml

from prompt2serviceflow.experiments.extractors import extract_service_references
from prompt2serviceflow.validators.schema_validation import load_document


def _argo_graph(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract task/template nodes and dependency edges from Argo resources."""

    nodes: dict[str, dict[str, Any]] = {}
    edges: set[tuple[str, str]] = set()
    errors: list[str] = []
    for document in documents:
        if not isinstance(document, dict) or document.get("kind") not in {
            "Workflow",
            "CronWorkflow",
        }:
            continue
        spec = document.get("spec") or {}
        if document.get("kind") == "CronWorkflow":
            spec = spec.get("workflowSpec") or {}
        templates = {
            item.get("name"): item
            for item in spec.get("templates", []) or []
            if isinstance(item, dict) and item.get("name")
        }
        if not templates:
            errors.append("workflow has no named templates")
        entrypoint = spec.get("entrypoint")
        if entrypoint and entrypoint not in templates:
            errors.append(f"entrypoint {entrypoint!r} does not reference a template")
        for template in templates.values():
            dag = template.get("dag") or {}
            for task in dag.get("tasks", []) or []:
                if not isinstance(task, dict) or not task.get("name"):
                    errors.append("DAG contains a task without a name")
                    continue
                task_name = str(task["name"])
                template_name = task.get("template")
                nodes[task_name] = {"name": task_name, "template": template_name}
                if template_name not in templates:
                    errors.append(
                        f"task {task_name!r} references missing template {template_name!r}"
                    )
                for predecessor in task.get("dependencies", []) or []:
                    edges.add((str(predecessor), task_name))
                depends = task.get("depends") or ""
                for predecessor in re.findall(r"[A-Za-z][A-Za-z0-9_.-]*", str(depends)):
                    if predecessor not in {"Succeeded", "Failed", "Errored", "Skipped", "Daemoned"}:
                        edges.add((predecessor.split(".", 1)[0], task_name))
            steps = template.get("steps") or []
            previous_group: list[str] = []
            for group in steps:
                current_group: list[str] = []
                for task in group if isinstance(group, list) else []:
                    if not isinstance(task, dict) or not task.get("name"):
                        continue
                    task_name = str(task["name"])
                    nodes[task_name] = {"name": task_name, "template": task.get("template")}
                    for predecessor in previous_group:
                        edges.add((predecessor, task_name))
                    current_group.append(task_name)
                previous_group = current_group
    known = set(nodes)
    for source, target in edges:
        if source not in known or target not in known:
            errors.append(f"edge {source!r}->{target!r} references an unknown task")
    return {
        "nodes": [nodes[key] for key in sorted(nodes)],
        "edges": [{"from": source, "to": target} for source, target in sorted(edges)],
        "errors": sorted(set(errors)),
    }


def _offline_lint(argo_text: str) -> dict[str, Any]:
    argo = shutil.which("argo")
    if not argo:
        return {"status": "unavailable", "reason": "argo not on PATH"}
    with tempfile.TemporaryDirectory(prefix="p2sf-direct-argo-") as temp:
        path = Path(temp) / "workflow.yaml"
        path.write_text(argo_text, encoding="utf-8")
        completed = subprocess.run(
            [argo, "lint", "--offline", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    return {
        "status": "pass" if completed.returncode == 0 else "fail",
        "message": completed.stdout.strip() or completed.stderr.strip(),
    }


def assess_direct_argo(argo_text: str, workspace: Path) -> dict[str, Any]:
    """Structural assessment + service-reference extraction for Argo YAML."""
    workspace = workspace.resolve()
    assessment: dict[str, Any] = {"yaml_parse": "fail", "documents": [], "gates": {}}
    try:
        documents = [document for document in yaml.safe_load_all(argo_text) if document is not None]
    except yaml.YAMLError as exc:
        assessment["error"] = str(exc)
        assessment["gates"] = {"G0": "fail", "G1": "skipped", "G2": "skipped", "G5": "skipped"}
        return assessment
    if not documents:
        assessment["error"] = "no YAML documents found"
        assessment["gates"] = {"G0": "fail", "G1": "skipped", "G2": "skipped", "G5": "skipped"}
        return assessment
    assessment["yaml_parse"] = "pass"
    kinds: dict[str, int] = {}
    malformed = 0
    wrong_api_version = 0
    for document in documents:
        if (
            not isinstance(document, dict)
            or not document.get("apiVersion")
            or not document.get("kind")
        ):
            malformed += 1
            continue
        if document.get("apiVersion") != "argoproj.io/v1alpha1":
            wrong_api_version += 1
        kind = document["kind"]
        kinds[kind] = kinds.get(kind, 0) + 1
    assessment["documents"] = {
        "count": len(documents),
        "kinds": kinds,
        "malformed": malformed,
        "wrong_api_version": wrong_api_version,
        "has_workflow": "Workflow" in kinds or "CronWorkflow" in kinds,
    }
    mapping_documents = [item for item in documents if isinstance(item, dict)]
    graph = _argo_graph(mapping_documents)
    assessment["graph"] = graph
    lint = _offline_lint(argo_text)
    assessment["argo_lint"] = lint

    catalog_ids = {path.stem for path in (workspace / "catalog" / "services").glob("*.yaml")}
    assessment["service_extraction"] = extract_service_references(argo_text, catalog_ids)
    g0_pass = malformed == 0 and wrong_api_version == 0 and assessment["documents"]["has_workflow"]
    g1_pass = g0_pass and not graph["errors"] and bool(graph["nodes"])
    g2_pass = bool(assessment["service_extraction"]["referenced_service_ids"])
    # Fail closed: an unavailable Argo CLI is not evidence of target validity.
    g5_pass = g0_pass and lint["status"] == "pass"
    assessment["gates"] = {
        "G0": "pass" if g0_pass else "fail",
        "G1": "pass" if g1_pass else "fail",
        "G2": "pass" if g2_pass else "fail",
        "G3": "not_applicable",
        "G4": "not_applicable",
        "G5": "pass" if g5_pass else "fail",
        "G6-Exec": "not_applicable",
        "G6-Assert": "not_applicable",
    }
    return assessment


def score_direct_argo(
    assessment: dict[str, Any],
    instance_dir: Path,
    workspace: Path,
) -> dict[str, Any]:
    """Score extracted service references against private candidate labels."""
    instance_dir = instance_dir.resolve()
    workspace = workspace.resolve()
    gold = load_document(instance_dir / "gold" / "serviceflow.yaml")
    candidate_labels = load_document(instance_dir / "gold" / "candidate_labels.yaml")
    gold_services = {binding["service_id"] for binding in gold["bindings"]}
    label_by_service: dict[str, str] = {}
    for candidate_set in candidate_labels["candidate_sets"]:
        for service_id, label in candidate_set["labels"].items():
            label_by_service[service_id] = label

    extraction = assessment.get("service_extraction", {})
    referenced = set(extraction.get("referenced_service_ids", []))
    catalog_ids = {path.stem for path in (workspace / "catalog" / "services").glob("*.yaml")}

    correct = referenced & gold_services
    distractor_confusion: dict[str, int] = {}
    out_of_catalog = 0
    for service_id in sorted(referenced - gold_services):
        if service_id not in catalog_ids:
            out_of_catalog += 1
            continue
        label = label_by_service.get(service_id)
        if label and label != "gold":
            distractor_confusion[label] = distractor_confusion.get(label, 0) + 1
    referenced_count = len(referenced)
    binding_by_intent = {
        binding["intent_id"]: binding["service_id"] for binding in gold["bindings"]
    }
    gold_edges = {
        (binding_by_intent.get(edge["from"]), binding_by_intent.get(edge["to"]))
        for edge in gold.get("control_flow", {}).get("edges", []) or []
    }
    gold_edges.discard((None, None))
    task_services = {
        node["name"]: node.get("template")
        for node in assessment.get("graph", {}).get("nodes", [])
        if node.get("template") in catalog_ids
    }
    submitted_edges = {
        (task_services.get(edge["from"]), task_services.get(edge["to"]))
        for edge in assessment.get("graph", {}).get("edges", [])
        if task_services.get(edge["from"]) and task_services.get(edge["to"])
    }
    edge_tp = len(submitted_edges & gold_edges)
    edge_precision = edge_tp / len(submitted_edges) if submitted_edges else 0.0
    edge_recall = edge_tp / len(gold_edges) if gold_edges else 0.0
    edge_f1 = (
        2 * edge_precision * edge_recall / (edge_precision + edge_recall)
        if edge_precision + edge_recall
        else 0.0
    )
    node_precision = len(correct) / referenced_count if referenced_count else 0.0
    node_recall = len(correct) / len(gold_services) if gold_services else 0.0
    node_f1 = (
        2 * node_precision * node_recall / (node_precision + node_recall)
        if node_precision + node_recall
        else 0.0
    )
    return {
        "service_grounded": bool(referenced),
        "not_service_grounded_note": (
            None if referenced else "no catalog service references extractable from the artifact"
        ),
        "referenced_service_count": referenced_count,
        "gold_service_count": len(gold_services),
        "service_precision": len(correct) / referenced_count if referenced_count else 0.0,
        "service_recall": len(correct) / len(gold_services) if gold_services else 0.0,
        "node_f1": node_f1,
        "edge_f1": edge_f1,
        "correct_services": sorted(correct),
        "distractor_confusion": dict(sorted(distractor_confusion.items())),
        "out_of_catalog_references": out_of_catalog,
        "yaml_parse": assessment.get("yaml_parse"),
        "documents": assessment.get("documents"),
        "gate_statuses": assessment.get("gates", {}),
        "full_pass_g0_g6": None,
        "full_pass_note": (
            "Direct-Argo outputs do not define the runtime package needed for G3/G4/G6; "
            "report applicable gates and structural graph metrics without treating N/A as pass."
        ),
    }
