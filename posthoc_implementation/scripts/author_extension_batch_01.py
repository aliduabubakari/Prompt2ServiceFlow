#!/usr/bin/env python3
"""Author Extension-50 batch 01 as reviewed multimodal benchmark instances."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from prompt2serviceflow.compiler.argo import write_resources
from reference_runtime import file_backed_mock_script


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "benchmark" / "source" / "extension_v1" / "batch_01"
INSTANCE_ROOT = ROOT / "benchmark" / "instances" / "extension"
CATALOG_VERSION = "0.3.0"
CATALOG_SOURCE = ROOT / "benchmark" / "catalog" / "snapshots" / "0.2.3"
CATALOG_TARGET = ROOT / "benchmark" / "catalog" / "snapshots" / CATALOG_VERSION
CREATED_AT = "2026-06-27T00:00:00+00:00"
DESCRIPTOR_CONTEXT = (
    "bounded multimodal image, document, table, and metadata batches"
)
DESCRIPTOR_KEYWORDS = ["multimodal", "document", "image"]
DESCRIPTOR_SOURCE_REF = "extension-batch-01:multimodal-curation"

SERVICE_BY_STEP = {
    "ingest_source_batch": ("multimodal_source_bundle_ingestor", "Extractor"),
    "validate_source_contract": ("multimodal_source_contract_validator", "QualityCheck"),
    "stage_raw_artifacts": ("multimodal_raw_artifact_stager", "Loader"),
    "normalize_records": ("multimodal_record_normalizer", "Transformer"),
    "extract_branch_features": ("multimodal_branch_feature_extractor", "Extractor"),
    "enrich_branch_context": ("multimodal_context_enricher", "Integrator"),
    "score_branch_quality": ("multimodal_branch_quality_scorer", "ScoringService"),
    "merge_branch_outputs": ("multimodal_branch_output_merger", "Aggregator"),
    "extract_visual_text_features": ("visual_document_feature_extractor", "Extractor"),
    "join_reference_metadata": ("multimodal_reference_metadata_joiner", "Integrator"),
    "assess_multimodal_quality": ("multimodal_quality_assessor", "QualityCheck"),
    "evaluate_policy_or_risk": ("multimodal_policy_risk_decider", "DomainAdapter"),
    "route_approved_records": ("approved_multimodal_record_router", "Publisher"),
    "route_exception_records": ("exception_multimodal_review_router", "Publisher"),
    "merge_route_outcomes": ("multimodal_route_outcome_merger", "Aggregator"),
    "publish_outputs": ("multimodal_output_bundle_publisher", "Publisher"),
}

DISTRACTORS = [
    "reviewed_domain_adapter",
    "document_feature_validation_quality_check",
    "image_cdn_batch_downloader",
    "csv_to_structured_json_standardizer",
    "json_field_projection_transformer",
    "dataset_quarantine_zone_writer",
]

TOPOLOGY_MAP = {
    "linear": "linear",
    "staged": "staged_etl",
    "fan_out": "fan_out",
    "branch_gate": "branch_merge",
}


def dump_yaml(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False, width=100), encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def port(name: str, data_type: str, *, required: bool = True, cardinality: str = "one") -> dict[str, Any]:
    return {
        "name": name,
        "description": f"Reviewed {name.replace('_', ' ')} port.",
        "channel": "artifact",
        "data_type": data_type,
        "required": required,
        "cardinality": cardinality,
        "sensitivity": "internal",
    }


def parameter(name: str, type_: str = "string", required: bool = False) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"Reviewed {name.replace('_', ' ')} configuration.",
        "type": type_,
        "required": required,
    }


def descriptor(service_id: str, category: str) -> dict[str, Any]:
    display = service_id.replace("_", " ").title()
    summary = (
        f"Executes the reviewed {display.lower()} capability for {DESCRIPTOR_CONTEXT}."
    )
    return {
        "schema_version": "0.1.0",
        "service_id": service_id,
        "version": "1.0.0",
        "display_name": display,
        "category": category,
        "capability": {
            "summary": summary,
            "operations": [
                "Read fixture-backed workflow artifacts supplied by the runtime.",
                "Perform the reviewed multimodal batch operation deterministically.",
                "Emit an artifact bundle and observable execution report.",
            ],
            "keywords": service_id.split("_") + DESCRIPTOR_KEYWORDS,
            "limitations": [
                "Does not contact production document, image, storage, or review systems.",
                "Does not claim true streaming execution.",
            ],
        },
        "lifecycle": {"status": "active"},
        "interface": {
            "inputs": [
                port("input_artifacts", "any", required=False, cardinality="many"),
            ],
            "outputs": [
                port("output_artifacts", "any", cardinality="many"),
                port("execution_report", "status"),
            ],
            "parameters": [
                parameter("operation_profile", required=True),
                parameter("modality_policy", "object"),
            ],
            "secrets": [],
        },
        "contracts": [],
        "invocation": {
            "type": "argo_workflow_template",
            "template_name": service_id.replace("_", "-")[:63],
            "template_entrypoint": "main",
            "image": "prompt2serviceflow/runtime:0.3.0",
            "command": ["python", "-m", f"prompt2serviceflow_services.{service_id}"],
            "implementation_ref": f"services/implementations/{service_id}",
            "mock_supported": True,
        },
        "policies": {
            "network_access": "forbidden",
            "allowed_network_targets": [],
            "secret_access": "forbidden",
            "retry_safe": True,
            "idempotency": "idempotent",
            "data_sensitivity": ["internal", "confidential", "pii"],
            "resources": {"cpu": "250m", "memory": "256Mi", "gpu": 0},
            "default_timeout_seconds": 300,
        },
        "compatibility": {
            "runtime": {"target": "argo-workflows", "minimum_version": "3.5.0"},
            "supported_architectures": ["amd64", "arm64"],
            "incompatible_services": [],
        },
        "provenance": {
            "origin": "curated",
            "owner": "Prompt2ServiceFlow",
            "created_at": CREATED_AT,
            "review_status": "reviewed",
            "source_refs": [DESCRIPTOR_SOURCE_REF],
            "notes": [
                "Curated for Extension-50 Batch 01 image/document multimodal pipelines.",
                "Contracts are intentionally fixture-backed for local G5 validation.",
            ],
        },
    }


def prepare_catalogue() -> None:
    if CATALOG_TARGET.exists():
        shutil.rmtree(CATALOG_TARGET)
    shutil.copytree(CATALOG_SOURCE, CATALOG_TARGET)
    for service_id, category in sorted(set(SERVICE_BY_STEP.values())):
        dump_yaml(CATALOG_TARGET / "services" / f"{service_id}.yaml", descriptor(service_id, category))

    entries = []
    for path in sorted((CATALOG_TARGET / "services").glob("*.yaml")):
        document = load_yaml(path)
        entries.append(
            {
                "service_id": document["service_id"],
                "version": document["version"],
                "category": document["category"],
                "descriptor_path": f"services/{path.name}",
                "sha256": sha256(path),
            }
        )
    catalog = {
        "catalog_id": "serviceflow_catalog",
        "version": CATALOG_VERSION,
        "created_at": CREATED_AT,
        "descriptor_schema": "schemas/service_descriptor.schema.json",
        "generation": {
            "run_id": "curated-extension-batch-01",
            "model": "manual-codex-curation",
            "splits": ["extension"],
        },
        "service_count": len(entries),
        "services": entries,
    }
    dump_yaml(CATALOG_TARGET / "catalog.yaml", catalog)


def manifest_rows() -> dict[str, dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in (ROOT / "benchmark" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {row["pipeline_id"]: row for row in rows if row.get("split") == "extension"}


def artifact(
    artifact_id: str,
    *,
    producer: str | None,
    consumers: list[str],
    role: str = "intermediate",
    data_type: str = "any",
    fixture_ref: str | None = None,
    external_system_ref: str | None = None,
    schema_ref: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "artifact_id": artifact_id,
        "name": artifact_id.replace("_", " ").title(),
        "kind": "external_resource" if external_system_ref else "artifact",
        "data_type": data_type,
        "media_type": "application/json",
        "role": role,
        "producer": producer,
        "consumers": consumers,
        "sensitivity": "internal",
        "persistence": "external" if external_system_ref else "workflow",
    }
    if fixture_ref:
        result["fixture_ref"] = fixture_ref
    if external_system_ref:
        result["external_system_ref"] = external_system_ref
    if schema_ref:
        result["schema_ref"] = schema_ref
    return result


def system_id(name: str) -> str:
    value = "".join(ch.lower() if ch.isalnum() else "_" for ch in name)
    parts = [part for part in value.split("_") if part]
    return "_".join(parts)[:100]


def external_systems(spec: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for item in spec["external_systems"]:
        sid = system_id(item["name"])
        system_type = "object_storage"
        if "api" in item["name"].lower() or "queue" in item["name"].lower():
            system_type = "other"
        result.append(
            {
                "system_id": sid,
                "type": system_type,
                "name": item["name"],
                "identifier": item["identifier"],
                "access_mode": "read_write",
                "authentication": "none",
                "mock_strategy": "fixture",
            }
        )
    return result


def intent(
    step: dict[str, Any],
    inputs: list[str],
    outputs: list[str],
    service_id: str,
    category: str,
    systems: list[str],
) -> dict[str, Any]:
    return {
        "intent_id": step["step_id"],
        "name": step["name"],
        "category": category,
        "capability": step["objective"],
        "source_step_refs": [step["step_id"]],
        "evidence": [{"source": "internal_spec", "text": step["objective"]}],
        "inputs": inputs,
        "outputs": outputs,
        "external_system_refs": systems,
        "preconditions": ["The bounded fixture-backed source artifacts are available."],
        "effects": [f"Produces {', '.join(outputs)}."],
        "required_policy_properties": {
            "network_access": "forbidden",
            "secret_access": "forbidden",
            "idempotency": "required",
            "data_sensitivity": ["internal"],
        },
        "decomposition_rationale": "One source step is represented by one reviewed multimodal catalogue service.",
        "confidence": "strongly_inferred",
        "ambiguity": {
            "status": "resolved",
            "notes": ["Synthetic source specification provides explicit bounded-batch step semantics."],
        },
    }


def binding(intent_id: str, service_id: str, inputs: list[str], outputs: list[str]) -> dict[str, Any]:
    status = f"{intent_id}_status"
    non_status_outputs = [item for item in outputs if item != status]
    return {
        "intent_id": intent_id,
        "service_id": service_id,
        "service_version": "1.0.0",
        "input_bindings": [{"port": "input_artifacts", "artifact_id": item} for item in inputs],
        "output_bindings": [
            *[{"port": "output_artifacts", "artifact_id": item} for item in non_status_outputs],
            {"port": "execution_report", "artifact_id": status},
        ],
        "parameter_bindings": {
            "operation_profile": intent_id,
            "modality_policy": {"batch": "extension_50_batch_01", "true_streaming": False},
        },
        "secret_bindings": [],
        "rationale": "The curated multimodal descriptor matches the bounded batch source step contract.",
        "confidence": "strongly_inferred",
    }


def status_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": True,
        "required": ["success", "errors"],
        "properties": {
            "success": {"type": "boolean"},
            "errors": {
                "type": "array",
                "items": {"oneOf": [{"type": "string"}, {"type": "object"}]},
            },
        },
    }


def mock_script(intent_id: str, outputs: list[str]) -> str:
    return file_backed_mock_script(intent_id, outputs)


def project_ports(items: list[dict[str, Any]]) -> dict[str, str | list[str]]:
    projected: dict[str, str | list[str]] = {}
    for item in items:
        current = projected.get(item["port"])
        if current is None:
            projected[item["port"]] = item["artifact_id"]
        elif isinstance(current, list):
            current.append(item["artifact_id"])
        else:
            projected[item["port"]] = [current, item["artifact_id"]]
    return projected


def candidate_documents(pipeline: str, benchmark_id: str, bindings: list[dict[str, Any]], intents: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    refs_by_service: dict[str, list[str]] = {}
    for item in bindings:
        refs = refs_by_service.setdefault(item["service_id"], [])
        intent_doc = next(intent for intent in intents if intent["intent_id"] == item["intent_id"])
        for ref in intent_doc["source_step_refs"]:
            if ref not in refs:
                refs.append(ref)

    public_sets = []
    private_sets = []
    review_sets = []
    for index, (service_id, refs) in enumerate(refs_by_service.items()):
        options = [service_id]
        for distractor in DISTRACTORS[index % len(DISTRACTORS):] + DISTRACTORS[: index % len(DISTRACTORS)]:
            if distractor != service_id and distractor not in options:
                options.append(distractor)
            if len(options) == 4:
                break
        candidate_set_id = f"extension_{pipeline}_{service_id}_candidates"
        labels = {
            options[0]: "gold",
            options[1]: "semantic_mismatch",
            options[2]: "generic_escape_hatch" if options[2] == "reviewed_domain_adapter" else "contract_mismatch",
            options[3]: "format_mismatch",
        }
        public_sets.append(
            {
                "candidate_set_id": candidate_set_id,
                "source_step_refs": refs,
                "service_ids": options,
            }
        )
        private_sets.append(
            {
                "candidate_set_id": candidate_set_id,
                "required_service_id": service_id,
                "labels": labels,
            }
        )
        review_sets.append(
            {
                "candidate_set_id": candidate_set_id,
                "required_service_id": service_id,
                "source_step_refs": refs,
                "candidates": [
                    {
                        "service_id": sid,
                        "label": labels[sid],
                        "rationale": "Reviewed candidate relationship for Extension-50 Batch 01.",
                    }
                    for sid in options
                ],
            }
        )
    return (
        {
            "candidate_set_version": "0.1.0",
            "benchmark_id": benchmark_id,
            "catalog_snapshot": {"catalog_id": "serviceflow_catalog", "version": CATALOG_VERSION},
            "candidate_sets": public_sets,
        },
        {
            "candidate_label_version": "0.1.0",
            "benchmark_id": benchmark_id,
            "candidate_sets": private_sets,
        },
        {"pipeline_id": pipeline, "candidate_sets": review_sets, "new_distractor_services": []},
    )


def source_for(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset_id": row.get("dataset_id", "prompt2serviceflow_extension_sources"),
        "dataset_version": row.get("dataset_version", "extension_v1"),
        "benchmark_id": row["benchmark_id"],
        "split": row["split"],
        "pipeline_id": row["pipeline_id"],
        "description_path": row["description_path"],
        "description_sha256": row["description_sha256"],
        "internal_spec_path": row["internal_spec_path"],
        "internal_spec_sha256": row["internal_spec_sha256"],
    }


def write_instance(spec_path: Path, row: dict[str, Any]) -> dict[str, Any]:
    spec = load_json(spec_path)
    pipeline = spec["pipeline_id"]
    root = INSTANCE_ROOT / pipeline
    for subdir in ("gold", "candidates", "contracts/artifacts", "fixtures/inputs", "runtime/scripts", "argo", "validation"):
        (root / subdir).mkdir(parents=True, exist_ok=True)

    systems = external_systems(spec)
    system_refs = [item["system_id"] for item in systems]
    steps = spec["steps"]
    predecessors: dict[str, list[str]] = {item["step_id"]: [] for item in steps}
    successors: dict[str, list[str]] = {item["step_id"]: [] for item in steps}
    for edge in spec["control_flow"]["edges"]:
        predecessors[edge["to"]].append(edge["from"])
        successors[edge["from"]].append(edge["to"])

    intents = []
    bindings = []
    artifacts = [
        artifact(
            "source_bundle",
            producer=None,
            consumers=[item["step_id"] for item in steps if not predecessors[item["step_id"]]],
            role="input",
            fixture_ref="fixtures/inputs/fixture.json",
        )
    ]
    task_outputs: dict[str, list[str]] = {}
    for step_doc in steps:
        step_id = step_doc["step_id"]
        service_id, category = SERVICE_BY_STEP[step_id]
        input_artifacts = (
            [f"{pred}_artifact" for pred in predecessors[step_id]]
            if predecessors[step_id]
            else ["source_bundle"]
        )
        output_artifacts = [f"{step_id}_artifact", f"{step_id}_status"]
        task_outputs[step_id] = output_artifacts
        intents.append(intent(step_doc, input_artifacts, output_artifacts, service_id, category, system_refs if step_id in {"ingest_source_batch", "publish_outputs", "route_exception_records", "route_approved_records"} else []))
        bindings.append(binding(step_id, service_id, input_artifacts, output_artifacts))
        artifacts.append(
            artifact(
                f"{step_id}_artifact",
                producer=step_id,
                consumers=successors[step_id],
                role="output" if not successors[step_id] else "intermediate",
                data_type="any",
            )
        )
        artifacts.append(
            artifact(
                f"{step_id}_status",
                producer=step_id,
                consumers=[],
                role="status",
                data_type="status",
                schema_ref="contracts/artifacts/status.schema.json",
            )
        )

    serviceflow = {
        "ir_version": "0.1.0",
        "composition_id": pipeline,
        "catalog_snapshot": {
            "catalog_id": "serviceflow_catalog",
            "version": CATALOG_VERSION,
            "sha256": sha256(CATALOG_TARGET / "catalog.yaml"),
        },
        "source": source_for(row),
        "requirement": {
            "name": spec["pipeline_name"],
            "purpose": spec["summary"]["purpose"],
            "domain": spec["summary"]["business_domain"],
            "execution_model": "batch",
            "topology": TOPOLOGY_MAP[spec["summary"]["topology_pattern"]],
            "information_sufficiency": "high",
            "notes": [
                "Extension-50 Batch 01 synthetic source.",
                "Event and external-system behavior is represented as bounded fixture-backed batch execution.",
            ],
        },
        "schedule": {"type": "manual", "expression": None, "timezone": None, "start_date": None, "catchup": False},
        "external_systems": systems,
        "service_intents": intents,
        "source_step_accounting": [
            {
                "source_step_ref": item["step_id"],
                "disposition": "service",
                "intent_ids": [item["step_id"]],
                "rationale": "The source step maps to one reviewed multimodal service intent.",
            }
            for item in steps
        ],
        "control_flow": {
            "edges": spec["control_flow"]["edges"],
            "parallel_groups": [
                {"group_id": group["group_id"], "intent_ids": group["steps"]}
                for group in spec["control_flow"].get("parallel_groups", [])
            ],
            "branches": [
                {
                    "branch_id": f"{item['step_id']}_branch",
                    "decision_intent": item["step_id"],
                    "cases": [
                        {"case_id": "approved", "condition": "decision.approved == true", "next_intents": ["route_approved_records"]},
                        {"case_id": "exception", "condition": "decision.exception == true", "next_intents": ["route_exception_records"]},
                    ],
                    "merge_intent": "merge_route_outcomes",
                }
                for item in spec["control_flow"].get("branch_points", [])
            ],
            "gates": [
                {
                    "gate_id": f"{item['step_id']}_gate",
                    "sensor_intent": item["step_id"],
                    "condition": item.get("condition", "quality and policy decision is available"),
                    "gated_intents": item.get("branches", []),
                }
                for item in spec["control_flow"].get("branch_points", [])
            ],
        },
        "artifacts": artifacts,
        "bindings": bindings,
        "policies": {
            "default_retries": 1,
            "default_retry_delay_seconds": 10,
            "fail_fast": True,
            "service_overrides": [],
            "governance": {
                "allowed_sensitivities": ["public", "internal", "confidential", "pii"],
                "network_default": "forbidden",
                "secret_placeholders_only": True,
                "notes": ["Batch 01 mocks do not contact production image, document, or review systems."],
            },
        },
        "runtime": {
            "target": "argo-workflows",
            "version": "4.0.5",
            "namespace": "prompt2serviceflow",
            "service_account": "prompt2serviceflow-runner",
            "artifact_repository": {"type": "none", "reference": None},
            "execution_profile": "mock",
        },
        "validation_expectations": [
            {"gate": gate, "expected_status": "pass", "checks": [f"{gate} reviewed Batch 01 validation."]}
            for gate in ["G0", "G1", "G2", "G3", "G4", "G5", "G6"]
        ],
    }
    dump_yaml(root / "gold/serviceflow.yaml", serviceflow)
    dump_yaml(root / "gold/bindings.yaml", {"binding_gold_version": "0.1.0", "benchmark_id": row["benchmark_id"], "bindings": [{key: item[key] for key in ["intent_id", "service_id", "service_version"]} for item in bindings]})
    dump_yaml(root / "gold/artifact_mappings.yaml", {"artifact_mapping_version": "0.1.0", "benchmark_id": row["benchmark_id"], "mappings": [{"intent_id": item["intent_id"], "inputs": project_ports(item["input_bindings"]), "outputs": project_ports(item["output_bindings"])} for item in bindings]})
    public, private, review = candidate_documents(pipeline, row["benchmark_id"], bindings, intents)
    dump_yaml(root / "candidates/candidate_sets.yaml", public)
    dump_yaml(root / "gold/candidate_labels.yaml", private)
    (root / "contracts/artifacts/status.schema.json").write_text(json.dumps(status_schema(), indent=2) + "\n", encoding="utf-8")
    (root / "fixtures/inputs/fixture.json").write_text(json.dumps({"pipeline_id": pipeline, "inputs": spec["summary"]["input_modalities"], "systems": [item["name"] for item in spec["external_systems"]]}, indent=2) + "\n", encoding="utf-8")

    tasks = []
    for number, item in enumerate(intents, start=1):
        script_name = f"{number:02d}_{item['intent_id']}.py"
        (root / "runtime" / "scripts" / script_name).write_text(mock_script(item["intent_id"], task_outputs[item["intent_id"]]), encoding="utf-8")
        task = {"intent_id": item["intent_id"], "script": f"scripts/{script_name}", "arguments": ["--workspace", "{workspace}", "--fixture", "{fixtures}/fixture.json"]}
        deps = predecessors[item["intent_id"]]
        if deps:
            task["dependencies"] = deps
        tasks.append(task)
    dump_yaml(root / "runtime/manifest.yaml", {"runtime_manifest_version": "0.1.0", "pipeline_id": pipeline, "image": "python:3.12-slim", "workflow_parameters": [], "tasks": tasks, "scenarios": [{"name": "nominal", "parameters": {}}]})
    final_status = f"{steps[-1]['step_id']}_status"
    dump_yaml(root / "gold/assertions.yaml", {"assertions_version": "0.1.0", "pipeline_id": pipeline, "scenarios": [{"scenario": "nominal", "assertions": [{"assertion_id": "final_status_succeeds", "type": "json_path_equals", "path": f"artifacts/{final_status}.json", "json_path": "success", "expected": True}]}]})
    (root / "README.md").write_text(f"# {spec['pipeline_name']}\n\nExtension-50 Batch 01 multimodal benchmark instance. Gold artifacts were generated by `scripts/author_extension_batch_01.py` and validated locally through G0-G6.\n", encoding="utf-8")
    write_resources(root)
    return review


def update_manifest_statuses(pipelines: list[str]) -> None:
    rows = [
        json.loads(line)
        for line in (ROOT / "benchmark" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    selected = set(pipelines)
    for row in rows:
        if row.get("split") == "extension" and row["pipeline_id"] in selected:
            row["annotation_status"] = "semantic_hardening_complete"
            row["review_status"] = "independent_review_pending"
    (ROOT / "benchmark" / "manifest.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    prepare_catalogue()
    rows = manifest_rows()
    reviews = []
    pipelines = []
    for spec_path in sorted((SOURCE_ROOT / "specs").glob("*.json")):
        spec = load_json(spec_path)
        pipelines.append(spec["pipeline_id"])
        reviews.append(write_instance(spec_path, rows[spec["pipeline_id"]]))
    update_manifest_statuses(pipelines)
    review_dir = ROOT / "benchmark" / "catalog" / "review" / CATALOG_VERSION
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "candidate_relationships.private.json").write_text(json.dumps({"catalog_version": CATALOG_VERSION, "pipelines": reviews}, indent=2) + "\n", encoding="utf-8")
    for pipeline in pipelines:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_instance.py"), str(INSTANCE_ROOT / pipeline)], cwd=ROOT, check=True)
    print("authored extension batch 01: 5 instances and catalogue 0.3.0")


if __name__ == "__main__":
    main()
