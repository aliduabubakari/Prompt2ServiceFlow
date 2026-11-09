#!/usr/bin/env python3
"""Author Validation-20 batch 01 as a reviewed, reproducible benchmark slice.

The source descriptions in this split are intentionally sparse.  This script keeps
the resulting inferences visible in ServiceFlowIR and creates a small immutable
catalogue extension rather than overloading an unrelated existing descriptor.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from prompt2serviceflow.compiler.argo import write_resources
from reference_runtime import file_backed_mock_script


ROOT = Path(__file__).resolve().parents[1]
CATALOG_VERSION = "0.2.0"
CREATED_AT = "2026-06-24T00:00:00+00:00"


def dump_yaml(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False, width=100), encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def port(name: str, data_type: str, *, channel: str = "artifact", required: bool = True) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"Reviewed {name.replace('_', ' ')} value.",
        "channel": channel,
        "data_type": data_type,
        "required": required,
        "cardinality": "one",
        "sensitivity": "internal",
    }


def descriptor(
    service_id: str,
    category: str,
    summary: str,
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    parameters: list[dict[str, Any]],
    *,
    network: str = "forbidden",
    secret: str = "forbidden",
) -> dict[str, Any]:
    return {
        "schema_version": "0.1.0",
        "service_id": service_id,
        "version": "1.0.0",
        "display_name": service_id.replace("_", " ").title(),
        "category": category,
        "capability": {
            "summary": summary,
            "operations": [summary],
            "keywords": service_id.split("_"),
            "limitations": ["Does not infer omitted domain policy, credentials, or target configuration."],
        },
        "lifecycle": {"status": "active"},
        "interface": {"inputs": inputs, "outputs": outputs, "parameters": parameters, "secrets": []},
        "contracts": [],
        "invocation": {
            "type": "argo_workflow_template",
            "template_name": service_id.replace("_", "-")[:63],
            "template_entrypoint": "main",
            "image": "prompt2serviceflow/runtime:0.2.0",
            "command": ["python", "-m", f"prompt2serviceflow_services.{service_id}"],
            "implementation_ref": f"services/implementations/{service_id}",
            "mock_supported": True,
        },
        "policies": {
            "network_access": network,
            "allowed_network_targets": ["database://*", "https://*", "sftp://*", "object://*"] if network != "forbidden" else [],
            "secret_access": secret,
            "retry_safe": True,
            "idempotency": "idempotent",
            "data_sensitivity": ["internal"],
            "resources": {"cpu": "250m", "memory": "256Mi", "gpu": 0},
            "default_timeout_seconds": 180,
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
            "source_refs": ["validation-batch-01:curated-extension"],
            "notes": ["Curated from sparse Validation-20 descriptions; bindings retain inference confidence."],
        },
    }


def parameter(name: str, type_: str = "string", required: bool = True) -> dict[str, Any]:
    return {"name": name, "description": f"Configuration for {name.replace('_', ' ')}.", "type": type_, "required": required}


def prepare_catalogue() -> None:
    source = ROOT / "benchmark/catalog/snapshots/0.1.1"
    target = ROOT / "benchmark/catalog/snapshots" / CATALOG_VERSION
    if not target.exists():
        shutil.copytree(source, target)
    services = {
        "filesystem_log_archive_and_delete": descriptor(
            "filesystem_log_archive_and_delete", "Maintenance", "Archives eligible log files before deleting their local copies.",
            [port("log_directory", "directory", channel="external_resource"), port("archive_destination", "object", channel="external_resource")],
            [port("archive_manifest", "object"), port("cleanup_status", "status")],
            [parameter("retention_days", "integer"), parameter("archive_prefix")], network="required", secret="optional",
        ),
        "json_status_payload_normalizer": descriptor(
            "json_status_payload_normalizer", "Transformer", "Normalizes an HTTP status payload into stable status rows.",
            [port("response_json", "json")], [port("normalized_status_rows", "table"), port("normalization_status", "status")],
            [parameter("status_mapping", "object")],
        ),
        "binary_report_bundle_archiver": descriptor(
            "binary_report_bundle_archiver", "Maintenance", "Compresses a binary report artifact into a durable bundle.",
            [port("report_file", "binary"), port("archive_destination", "object", channel="external_resource")],
            [port("report_bundle", "binary"), port("archive_status", "status")],
            [parameter("archive_name"), parameter("archive_format")], network="required", secret="optional",
        ),
        "sqlite_health_snapshot_loader": descriptor(
            "sqlite_health_snapshot_loader", "Loader", "Stores normalized health-status rows in a SQLite metrics snapshot.",
            [port("normalized_status_rows", "table"), port("metrics_store", "object", channel="external_resource")],
            [port("health_snapshot_table", "table"), port("load_status", "status")],
            [parameter("table_name")],
        ),
        "tabular_kpi_pdf_report_renderer": descriptor(
            "tabular_kpi_pdf_report_renderer", "ReportGenerator", "Renders a PDF KPI report from a tabular extract.",
            [port("kpi_extract", "csv")], [port("pdf_report", "binary"), port("render_status", "status")],
            [parameter("report_title"), parameter("output_path")],
        ),
        "object_storage_bundle_publisher": descriptor(
            "object_storage_bundle_publisher", "Publisher", "Publishes an existing report bundle to an approved object-storage location.",
            [port("report_bundle", "binary"), port("publish_destination", "object", channel="external_resource")],
            [port("publication_status", "status")], [parameter("destination_prefix")], network="required", secret="optional",
        ),
        "feature_store_table_extractor": descriptor(
            "feature_store_table_extractor", "Extractor", "Reads a named customer feature table from a bound feature store.",
            [port("feature_store", "object", channel="external_resource")], [port("customer_features", "table"), port("extraction_status", "status")],
            [parameter("feature_table")], network="required", secret="optional",
        ),
        "model_registry_artifact_fetcher": descriptor(
            "model_registry_artifact_fetcher", "Extractor", "Fetches a versioned model artifact from a bound model registry.",
            [port("model_registry", "object", channel="external_resource")], [port("model_artifact", "model"), port("fetch_status", "status")],
            [parameter("model_name"), parameter("model_version")], network="required", secret="optional",
        ),
        "tabular_model_scorer": descriptor(
            "tabular_model_scorer", "ScoringService", "Applies a bound model artifact to customer feature rows and emits predictions.",
            [port("customer_features", "table"), port("model_artifact", "model")], [port("prediction_table", "table"), port("scoring_status", "status")],
            [parameter("prediction_column")],
        ),
        "prediction_table_database_loader": descriptor(
            "prediction_table_database_loader", "Loader", "Writes a prediction table to the configured durable prediction sink.",
            [port("prediction_table", "table"), port("prediction_store", "object", channel="external_resource")], [port("write_status", "status")],
            [parameter("target_table")], network="required", secret="optional",
        ),
    }
    for service_id, document in services.items():
        dump_yaml(target / "services" / f"{service_id}.yaml", document)
    entries = []
    for path in sorted((target / "services").glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        entries.append({"service_id": document["service_id"], "version": document["version"], "category": document["category"], "descriptor_path": f"services/{path.name}", "sha256": sha256(path)})
    catalog = {
        "catalog_id": "serviceflow_catalog", "version": CATALOG_VERSION, "created_at": CREATED_AT,
        "descriptor_schema": "schemas/service_descriptor.schema.json",
        "generation": {"run_id": "curated-validation-batch-01", "model": "manual-curation", "splits": ["validation"]},
        "service_count": len(entries), "services": entries,
    }
    dump_yaml(target / "catalog.yaml", catalog)


def artifact(artifact_id: str, data_type: str, producer: str | None, consumers: list[str], *, role: str = "intermediate", external: str | None = None) -> dict[str, Any]:
    result = {"artifact_id": artifact_id, "name": artifact_id.replace("_", " ").title(), "kind": "external_resource" if external else "artifact", "data_type": data_type, "role": "input" if external else role, "producer": producer, "consumers": consumers, "sensitivity": "internal", "persistence": "external" if external else "workflow"}
    if external:
        result["external_system_ref"] = external
    return result


def intent(intent_id: str, category: str, step: str, inputs: list[str], outputs: list[str], systems: list[str], *, confidence: str = "strongly_inferred") -> dict[str, Any]:
    return {
        "intent_id": intent_id, "name": intent_id.replace("_", " ").title(), "category": category,
        "capability": f"Perform the reviewed {intent_id.replace('_', ' ')} capability.", "source_step_refs": [step],
        "evidence": [{"source": "internal_spec", "text": f"Validation source step: {step}."}],
        "inputs": inputs, "outputs": outputs, "external_system_refs": systems,
        "preconditions": ["The explicitly bound inputs and configuration are available."],
        "effects": [f"The declared {', '.join(outputs)} artifact(s) are produced."],
        "required_policy_properties": {"network_access": "required" if systems else "forbidden", "secret_access": "optional" if systems else "forbidden", "idempotency": "preferred", "data_sensitivity": ["internal"]},
        "decomposition_rationale": "One source step is represented by one observable, contract-bound service intent.",
        "confidence": confidence,
        "ambiguity": {"status": "resolved", "notes": ["The source description omits implementation details; curated defaults are isolated in fixture and parameter bindings."]},
    }


def binding(intent_id: str, service_id: str, inputs: dict[str, str], outputs: dict[str, str], parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent_id": intent_id, "service_id": service_id, "service_version": "1.0.0",
        "input_bindings": [{"port": key, "artifact_id": value} for key, value in inputs.items()],
        "output_bindings": [{"port": key, "artifact_id": value} for key, value in outputs.items()],
        "parameter_bindings": parameters, "secret_bindings": [],
        "rationale": "The descriptor exposes the required inputs, outputs, and side effect without assuming omitted source details.",
        "confidence": "strongly_inferred",
    }


def systems(items: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    return [{"system_id": item[0], "type": item[1], "name": item[2], "identifier": item[0], "access_mode": "read_write", "authentication": "unknown", "mock_strategy": "fixture"} for item in items]


def serviceflow(pipeline: str, purpose: str, topology: str, ext: list[dict[str, Any]], intents: list[dict[str, Any]], artifacts: list[dict[str, Any]], bindings: list[dict[str, Any]], edges: list[tuple[str, str]], schedule: bool) -> dict[str, Any]:
    manifest = next(json.loads(line) for line in (ROOT / "benchmark/manifest.jsonl").read_text().splitlines() if json.loads(line)["pipeline_id"] == pipeline)
    catalog_path = ROOT / "benchmark/catalog/snapshots" / CATALOG_VERSION / "catalog.yaml"
    return {
        "ir_version": "0.1.0", "composition_id": pipeline, "catalog_snapshot": {"catalog_id": "serviceflow_catalog", "version": CATALOG_VERSION, "sha256": sha256(catalog_path)},
        "source": {
            "dataset_id": "zenodo_pipeline_descriptions",
            "dataset_version": "v1.0.0",
            **{key: manifest[key] for key in ["benchmark_id", "split", "pipeline_id", "description_path", "description_sha256", "internal_spec_path", "internal_spec_sha256"]},
        },
        "requirement": {"name": pipeline.replace("_", " ").title(), "purpose": purpose, "domain": "validation_holdout", "execution_model": "batch", "topology": topology, "information_sufficiency": "low", "notes": ["Validation-20 source is sparse; all bindings are strongly inferred and must not be used to tune a system evaluated on this split."]},
        "schedule": {"type": "cron", "expression": "0 0 * * *", "timezone": "UTC", "start_date": None, "catchup": False} if schedule else {"type": "manual", "expression": None, "timezone": None, "start_date": None, "catchup": False},
        "external_systems": ext, "service_intents": intents,
        "source_step_accounting": [{"source_step_ref": item["source_step_refs"][0], "disposition": "service", "intent_ids": [item["intent_id"]], "rationale": "The source specification declares this executable data-processing step."} for item in intents],
        "control_flow": {"edges": [{"from": a, "to": b} for a, b in edges], "parallel_groups": [], "branches": [], "gates": []},
        "artifacts": artifacts, "bindings": bindings,
        "policies": {"default_retries": 1, "default_retry_delay_seconds": 10, "fail_fast": True, "service_overrides": [], "governance": {"allowed_sensitivities": ["internal", "confidential"], "network_default": "optional", "secret_placeholders_only": True, "notes": ["Mock fixtures contain no credentials or production records."]}},
        "runtime": {"target": "argo-workflows", "version": "4.0.5", "namespace": "prompt2serviceflow", "service_account": "prompt2serviceflow-runner", "artifact_repository": {"type": "none", "reference": None}, "execution_profile": "mock"},
        "validation_expectations": [{"gate": gate, "expected_status": "pass", "checks": [f"{gate} deterministic reviewed validation."]} for gate in ["G0", "G1", "G2", "G3", "G4", "G5", "G6"]],
    }


def mock_script(task: str, outputs: list[str]) -> str:
    return file_backed_mock_script(task, outputs)


def candidates(pipeline: str, bound: list[str]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    mismatches = ["reviewed_domain_adapter", "temporary_resource_cleanup", "csv_to_structured_json_standardizer", "tabular_dataset_database_loader", "http_json_request_extractor", "report_artifact_object_storage_archiver"]
    public, private, review_sets = [], [], []
    for number, service_id in enumerate(dict.fromkeys(bound)):
        options = [service_id, mismatches[number % len(mismatches)], mismatches[(number + 1) % len(mismatches)]]
        options = list(dict.fromkeys(options))
        while len(options) < 3:
            options.append("reviewed_domain_adapter")
            options = list(dict.fromkeys(options))
        set_id = f"validation_{pipeline}_{service_id}_candidates"
        refs = []
        public.append({"candidate_set_id": set_id, "source_step_refs": refs, "service_ids": options})
        private.append({"candidate_set_id": set_id, "required_service_id": service_id, "labels": {options[0]: "gold", options[1]: "semantic_mismatch", options[2]: "generic_escape_hatch"}})
        review_sets.append({"candidate_set_id": set_id, "required_service_id": service_id, "source_step_refs": refs, "candidates": [{"service_id": options[0], "label": "gold", "rationale": "Reviewed contract match."}, {"service_id": options[1], "label": "semantic_mismatch", "rationale": "Capability overlap without the required contract."}, {"service_id": options[2], "label": "generic_escape_hatch", "rationale": "Generic alternative is less specific than the reviewed service."}]})
    # Source refs are filled from the authoritative ServiceFlowIR after it is constructed.
    return {"candidate_set_version": "0.1.0", "benchmark_id": f"validation:{pipeline}", "catalog_snapshot": {"catalog_id": "serviceflow_catalog", "version": CATALOG_VERSION}, "candidate_sets": public}, {"candidate_label_version": "0.1.0", "benchmark_id": f"validation:{pipeline}", "candidate_sets": private}, {"pipeline_id": pipeline, "candidate_sets": review_sets, "new_distractor_services": [], "review_notes": ["Curated for Validation-20 batch 01; labels are private benchmark gold."]}


def write_instance(flow: dict[str, Any], task_outputs: dict[str, list[str]], fixture: dict[str, Any]) -> dict[str, Any]:
    pipeline = flow["source"]["pipeline_id"]
    root = ROOT / "benchmark/instances/validation" / pipeline
    dump_yaml(root / "gold/serviceflow.yaml", flow)
    bound = [item["service_id"] for item in flow["bindings"]]
    public, private, review = candidates(pipeline, bound)
    intent_by_service = {item["service_id"]: item["intent_id"] for item in flow["bindings"]}
    intent_refs = {item["intent_id"]: item["source_step_refs"] for item in flow["service_intents"]}
    for candidate_set in public["candidate_sets"]:
        candidate_set["source_step_refs"] = intent_refs[intent_by_service[candidate_set["candidate_set_id"].removeprefix(f"validation_{pipeline}_").removesuffix("_candidates")]]
    for candidate_set in review["candidate_sets"]:
        candidate_set["source_step_refs"] = public["candidate_sets"][review["candidate_sets"].index(candidate_set)]["source_step_refs"]
    dump_yaml(root / "candidates/candidate_sets.yaml", public)
    dump_yaml(root / "gold/candidate_labels.yaml", private)
    dump_yaml(root / "gold/bindings.yaml", {"binding_gold_version": "0.1.0", "benchmark_id": flow["source"]["benchmark_id"], "bindings": [{key: item[key] for key in ["intent_id", "service_id", "service_version"]} for item in flow["bindings"]]})
    dump_yaml(root / "gold/artifact_mappings.yaml", {"artifact_mapping_version": "0.1.0", "benchmark_id": flow["source"]["benchmark_id"], "mappings": [{"intent_id": item["intent_id"], "inputs": {x["port"]: x["artifact_id"] for x in item["input_bindings"]}, "outputs": {x["port"]: x["artifact_id"] for x in item["output_bindings"]}} for item in flow["bindings"]]})
    tasks = []
    for number, item in enumerate(flow["service_intents"], start=1):
        task_id = item["intent_id"]
        filename = f"{number:02d}_{task_id}.py"
        (root / "runtime/scripts" / filename).write_text(mock_script(task_id, task_outputs[task_id]), encoding="utf-8")
        predecessors = [edge["from"] for edge in flow["control_flow"]["edges"] if edge["to"] == task_id]
        task = {"intent_id": task_id, "script": f"scripts/{filename}", "arguments": ["--workspace", "{workspace}", "--fixture", "{fixtures}/fixture.json"]}
        if predecessors:
            task["dependencies"] = predecessors
        tasks.append(task)
    manifest = {"runtime_manifest_version": "0.1.0", "pipeline_id": pipeline, "image": "python:3.12-slim", "workflow_parameters": [], "tasks": tasks, "scenarios": [{"name": "nominal", "parameters": {}}]}
    if flow["schedule"]["type"] == "cron":
        manifest["cron"] = {"schedule": flow["schedule"]["expression"], "timezone": "UTC"}
    dump_yaml(root / "runtime/manifest.yaml", manifest)
    (root / "fixtures/inputs/fixture.json").write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    final_status = task_outputs[flow["service_intents"][-1]["intent_id"]][-1]
    dump_yaml(root / "gold/assertions.yaml", {"assertions_version": "0.1.0", "pipeline_id": pipeline, "scenarios": [{"scenario": "nominal", "assertions": [{"assertion_id": "final_status_succeeds", "type": "json_path_equals", "path": f"artifacts/{final_status}.json", "json_path": "success", "expected": True}]}]})
    (root / "README.md").write_text(f"# {pipeline}\n\nValidation-20 batch 01. Source evidence is low-information; service bindings are explicitly marked strongly inferred. The runtime uses deterministic, task-specific mock scripts and does not claim external-system execution.\n", encoding="utf-8")
    write_resources(root)
    return review


def main() -> None:
    prepare_catalogue()
    # Each tuple is (service intent ID, category, source step, input artifacts, output artifacts, external systems, service ID, input port mapping, output port mapping, parameters).
    definitions = []
    definitions.append((
        "val_csv_to_warehouse_daily", "Load daily sales CSV after file availability and schema validation.", "linear", True,
        systems([("sftp_drop_zone", "sftp", "SFTP daily sales drop zone"), ("warehouse", "database", "PostgreSQL warehouse")]),
        [("detect_daily_file", "Sensor", "detect_daily_file", ["sftp_drop_zone_resource"], ["availability_decision", "availability_status"], ["sftp_drop_zone"], "file_location_availability_sensor", {"file_location_resource": "sftp_drop_zone_resource"}, {"availability_decision": "availability_decision", "check_status": "availability_status"}, {"location_type": "sftp", "path": "/sales", "availability_condition": "contains_matching_files", "filename_pattern": "daily_sales.csv"}),
         ("validate_columns", "Extractor", "validate_columns", ["daily_sales_csv"], ["validated_sales_frame", "validated_sales_metadata", "validation_status"], [], "csv_tabular_schema_validating_loader", {"csv_file": "daily_sales_csv"}, {"validated_dataset": "validated_sales_frame", "validated_data_object": "validated_sales_metadata", "validation_status": "validation_status"}, {"required_columns": ["sale_id", "amount"], "output_path": "validated-sales.json"}),
         ("load_sales_table", "Loader", "load_sales_table", ["validated_sales_metadata", "warehouse_resource"], ["sales_load_status"], ["warehouse"], "tabular_dataset_database_loader", {"ingested_data_object": "validated_sales_metadata", "target_database": "warehouse_resource"}, {"load_status": "sales_load_status"}, {"target_table": "sales_fact", "write_mode": "upsert"})],
        {"sftp_drop_zone_resource": ("object", None, "sftp_drop_zone"), "warehouse_resource": ("object", None, "warehouse"), "daily_sales_csv": ("csv", None, None)}, {"source": "daily_sales.csv"},
    ))
    definitions.append((
        "val_log_rotation_cleanup", "Archive expired application logs before deleting local copies.", "linear", True,
        systems([("local_log_directory", "filesystem", "Local application log directory"), ("log_archive", "object_storage", "Object-storage log archive")]),
        [("find_expired_logs", "Sensor", "find_expired_logs", ["log_location_resource"], ["availability_decision", "availability_status"], ["local_log_directory"], "file_location_availability_sensor", {"file_location_resource": "log_location_resource"}, {"availability_decision": "availability_decision", "check_status": "availability_status"}, {"location_type": "filesystem", "path": "/var/log/app", "availability_condition": "contains_matching_files", "filename_pattern": "*.log*"}),
         ("archive_and_delete_logs", "Maintenance", "archive_and_delete_logs", ["local_log_directory_resource", "log_archive_resource"], ["archive_manifest", "cleanup_status"], ["local_log_directory", "log_archive"], "filesystem_log_archive_and_delete", {"log_directory": "local_log_directory_resource", "archive_destination": "log_archive_resource"}, {"archive_manifest": "archive_manifest", "cleanup_status": "cleanup_status"}, {"retention_days": 30, "archive_prefix": "logs/"})],
        {"log_location_resource": ("object", None, "local_log_directory"), "local_log_directory_resource": ("directory", None, "local_log_directory"), "log_archive_resource": ("object", None, "log_archive")}, {"expired": ["app.log.1"]},
    ))
    definitions.append((
        "val_api_health_snapshot", "Poll a partner API, normalize its status response, and persist a health snapshot.", "linear", False,
        systems([("partner_api", "http_api", "Partner HTTP API"), ("metrics_store", "database", "SQLite metrics store")]),
        [("poll_partner_api", "Extractor", "poll_partner_api", [], ["status_response_json", "poll_status"], ["partner_api"], "http_json_request_extractor", {}, {"response_json": "status_response_json", "extraction_status": "poll_status"}, {"endpoint": "https://partner.example.test/status", "method": "GET"}),
         ("normalize_status_payload", "Transformer", "normalize_status_payload", ["status_response_json"], ["normalized_status_rows", "normalization_status"], [], "json_status_payload_normalizer", {"response_json": "status_response_json"}, {"normalized_status_rows": "normalized_status_rows", "normalization_status": "normalization_status"}, {"status_mapping": {"status": "status"}}),
         ("store_health_snapshot", "Loader", "store_health_snapshot", ["normalized_status_rows", "metrics_store_resource"], ["health_snapshot_table", "snapshot_status"], ["metrics_store"], "sqlite_health_snapshot_loader", {"normalized_status_rows": "normalized_status_rows", "metrics_store": "metrics_store_resource"}, {"health_snapshot_table": "health_snapshot_table", "load_status": "snapshot_status"}, {"table_name": "health_snapshot"})],
        {"metrics_store_resource": ("object", None, "metrics_store")}, {"status": "healthy"},
    ))
    definitions.append((
        "val_weekly_report_packager", "Create a weekly PDF report from KPI extracts, package it, and publish the bundle.", "linear", True,
        systems([("warehouse", "database", "Analytics warehouse"), ("report_storage", "object_storage", "Report object storage")]),
        [("collect_kpi_extracts", "Extractor", "collect_kpi_extracts", ["warehouse_resource"], ["kpi_extract", "extract_status"], ["warehouse"], "database_csv_snapshot_exporter", {"source_database": "warehouse_resource"}, {"csv_snapshot": "kpi_extract", "export_status": "extract_status"}, {"export_spec": {"table": "weekly_kpis"}, "output_path": "weekly-kpis.csv"}),
         ("render_pdf_report", "ReportGenerator", "render_pdf_report", ["kpi_extract"], ["weekly_report_pdf", "render_status"], [], "tabular_kpi_pdf_report_renderer", {"kpi_extract": "kpi_extract"}, {"pdf_report": "weekly_report_pdf", "render_status": "render_status"}, {"report_title": "Weekly KPI Report", "output_path": "weekly-report.pdf"}),
         ("compress_report_bundle", "Maintenance", "compress_report_bundle", ["weekly_report_pdf", "report_storage_resource"], ["report_bundle", "archive_status"], ["report_storage"], "binary_report_bundle_archiver", {"report_file": "weekly_report_pdf", "archive_destination": "report_storage_resource"}, {"report_bundle": "report_bundle", "archive_status": "archive_status"}, {"archive_format": "zip", "archive_name": "weekly-report.zip"}),
         ("publish_bundle", "Publisher", "publish_bundle", ["report_bundle", "report_storage_resource"], ["publication_status"], ["report_storage"], "object_storage_bundle_publisher", {"report_bundle": "report_bundle", "publish_destination": "report_storage_resource"}, {"publication_status": "publication_status"}, {"destination_prefix": "published/"})],
        {"warehouse_resource": ("object", None, "warehouse"), "report_storage_resource": ("object", None, "report_storage")}, {"week": "2026-W25"},
    ))
    definitions.append((
        "val_batch_model_scoring", "Load customer features and a model artifact, score customers, then write predictions.", "fan_out_fan_in", True,
        systems([("feature_store", "database", "Customer feature store"), ("model_registry", "other", "Model registry"), ("prediction_store", "database", "Prediction database")]),
        [("load_feature_table", "Extractor", "load_feature_table", ["feature_store_resource"], ["customer_features", "feature_extract_status"], ["feature_store"], "feature_store_table_extractor", {"feature_store": "feature_store_resource"}, {"customer_features": "customer_features", "extraction_status": "feature_extract_status"}, {"feature_table": "customer_features"}),
         ("load_model_artifact", "Extractor", "load_model_artifact", ["model_registry_resource"], ["churn_model", "model_fetch_status"], ["model_registry"], "model_registry_artifact_fetcher", {"model_registry": "model_registry_resource"}, {"model_artifact": "churn_model", "fetch_status": "model_fetch_status"}, {"model_name": "churn", "model_version": "approved"}),
         ("score_customers", "ScoringService", "score_customers", ["customer_features", "churn_model"], ["prediction_table", "scoring_status"], [], "tabular_model_scorer", {"customer_features": "customer_features", "model_artifact": "churn_model"}, {"prediction_table": "prediction_table", "scoring_status": "scoring_status"}, {"prediction_column": "churn_score"}),
         ("write_predictions", "Loader", "write_predictions", ["prediction_table", "prediction_store_resource"], ["prediction_write_status"], ["prediction_store"], "prediction_table_database_loader", {"prediction_table": "prediction_table", "prediction_store": "prediction_store_resource"}, {"write_status": "prediction_write_status"}, {"target_table": "customer_predictions"})],
        {"feature_store_resource": ("object", None, "feature_store"), "model_registry_resource": ("object", None, "model_registry"), "prediction_store_resource": ("object", None, "prediction_store")}, {"customers": 3},
    ))
    reviews = []
    for pipeline, purpose, topology, scheduled, ext, rows, seed_artifacts, fixture in definitions:
        intents = [intent(a, b, c, d, e, f) for a, b, c, d, e, f, *_ in rows]
        bindings = [binding(a, g, h, i, j) for a, _, _, _, _, _, g, h, i, j in rows]
        artifact_defs = [artifact(key, typ, producer, [], external=external) for key, (typ, producer, external) in seed_artifacts.items()]
        for row in rows:
            intent_id, _, _, _, outputs, *_ = row
            for output in outputs:
                descriptor_output = next(item for item in bindings if item["intent_id"] == intent_id)["output_bindings"]
                port_name = next(item["port"] for item in descriptor_output if item["artifact_id"] == output)
                service_id = next(item["service_id"] for item in bindings if item["intent_id"] == intent_id)
                document = yaml.safe_load((ROOT / "benchmark/catalog/snapshots" / CATALOG_VERSION / "services" / f"{service_id}.yaml").read_text())
                data_type = next(item["data_type"] for item in document["interface"]["outputs"] if item["name"] == port_name)
                consumers = [other[0] for other in rows if output in other[3]]
                artifact_defs.append(artifact(output, data_type, intent_id, consumers, role="output" if not consumers else "intermediate"))
        edges = [(rows[index][0], rows[index + 1][0]) for index in range(len(rows) - 1)]
        if pipeline == "val_batch_model_scoring":
            edges = [("load_feature_table", "score_customers"), ("load_model_artifact", "score_customers"), ("score_customers", "write_predictions")]
        flow = serviceflow(pipeline, purpose, topology, ext, intents, artifact_defs, bindings, edges, scheduled)
        task_outputs = {item["intent_id"]: item["outputs"] for item in intents}
        reviews.append(write_instance(flow, task_outputs, fixture))
    review_dir = ROOT / "benchmark/catalog/review" / CATALOG_VERSION
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "candidate_relationships.private.json").write_text(json.dumps({"catalog_version": CATALOG_VERSION, "pipelines": reviews}, indent=2) + "\n", encoding="utf-8")
    print("authored validation batch 01: 5 instances and catalogue 0.2.0")


if __name__ == "__main__":
    main()
