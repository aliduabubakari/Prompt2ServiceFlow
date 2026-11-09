#!/usr/bin/env python3
"""Author Validation-20 batch 02 as a reviewed benchmark slice.

Batch 02 extends the manually curated validation holdout with moderate
linear, fan-out, sensor-gated, and branch/router topologies.  The source
descriptions remain sparse, so every binding is marked strongly inferred and
the new service descriptors live in a separate immutable catalogue snapshot.
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import author_validation_batch_01 as base
import yaml

from prompt2serviceflow.compiler.argo import write_resources


ROOT = Path(__file__).resolve().parents[1]
CATALOG_VERSION = "0.2.1"
BASE_CATALOG_VERSION = "0.2.0"
CREATED_AT = "2026-06-25T00:00:00+00:00"

base.CATALOG_VERSION = CATALOG_VERSION
base.CREATED_AT = CREATED_AT


def dump_yaml(path: Path, document: Any) -> None:
    base.dump_yaml(path, document)


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
    document = base.descriptor(
        service_id,
        category,
        summary,
        inputs,
        outputs,
        parameters,
        network=network,
        secret=secret,
    )
    document["invocation"]["image"] = "prompt2serviceflow/runtime:0.2.1"
    document["provenance"]["created_at"] = CREATED_AT
    document["provenance"]["source_refs"] = ["validation-batch-02:curated-extension"]
    document["provenance"]["notes"] = [
        "Curated from sparse Validation-20 batch 02 descriptions; bindings retain inference confidence."
    ]
    return document


def prepare_catalogue() -> None:
    source = ROOT / "benchmark/catalog/snapshots" / BASE_CATALOG_VERSION
    target = ROOT / "benchmark/catalog/snapshots" / CATALOG_VERSION
    if not target.exists():
        shutil.copytree(source, target)

    port = base.port
    parameter = base.parameter
    services = {
        "crm_api_record_extractor": descriptor(
            "crm_api_record_extractor",
            "Extractor",
            "Extracts customer records from a configured CRM API export endpoint.",
            [port("crm_api", "object", channel="external_resource")],
            [port("crm_records", "json"), port("extraction_status", "status")],
            [parameter("object_name"), parameter("updated_since", required=False)],
            network="required",
            secret="optional",
        ),
        "customer_profile_field_normalizer": descriptor(
            "customer_profile_field_normalizer",
            "Transformer",
            "Normalizes CRM customer fields into a stable customer-profile table.",
            [port("crm_records", "json")],
            [port("normalized_profiles", "table"), port("normalization_status", "status")],
            [parameter("normalization_profile", "object")],
        ),
        "customer_profile_deduplicator": descriptor(
            "customer_profile_deduplicator",
            "Reconciler",
            "Deduplicates normalized customer profiles with configured identity keys.",
            [port("normalized_profiles", "table")],
            [port("deduplicated_profiles", "table"), port("dedup_status", "status")],
            [parameter("identity_keys", "array"), parameter("survivorship_policy")],
        ),
        "customer_profile_table_loader": descriptor(
            "customer_profile_table_loader",
            "Loader",
            "Loads deduplicated customer profiles into a warehouse profile table.",
            [
                port("deduplicated_profiles", "table"),
                port("customer_warehouse", "object", channel="external_resource"),
            ],
            [port("profile_table", "table"), port("load_status", "status")],
            [parameter("target_table"), parameter("write_mode")],
            network="required",
            secret="optional",
        ),
        "profile_refresh_summary_emitter": descriptor(
            "profile_refresh_summary_emitter",
            "ReportGenerator",
            "Emits a bounded operational summary for a completed customer-profile refresh.",
            [port("profile_table", "table")],
            [port("refresh_summary", "json"), port("summary_status", "status")],
            [parameter("summary_name")],
        ),
        "image_cdn_batch_downloader": descriptor(
            "image_cdn_batch_downloader",
            "Extractor",
            "Downloads a bounded batch of product images from an image CDN.",
            [port("image_cdn", "object", channel="external_resource")],
            [port("raw_product_images", "array"), port("download_status", "status")],
            [parameter("prefix"), parameter("max_images", "integer")],
            network="required",
            secret="optional",
        ),
        "image_thumbnail_renderer": descriptor(
            "image_thumbnail_renderer",
            "Transformer",
            "Renders a configured thumbnail size from a batch of product images.",
            [port("raw_product_images", "array")],
            [port("thumbnail_bundle", "binary"), port("render_status", "status")],
            [parameter("size_label"), parameter("width", "integer"), parameter("height", "integer")],
        ),
        "partner_file_checksum_validator": descriptor(
            "partner_file_checksum_validator",
            "QualityCheck",
            "Validates an arrived partner file against an expected checksum record.",
            [port("partner_file", "csv"), port("checksum_record", "object")],
            [port("verified_partner_file", "csv"), port("checksum_status", "status")],
            [parameter("algorithm")],
        ),
        "invoice_batch_validator": descriptor(
            "invoice_batch_validator",
            "QualityCheck",
            "Validates invoice rows and separates valid and invalid invoice records.",
            [port("invoice_batch", "table")],
            [
                port("valid_invoice_rows", "table"),
                port("invalid_invoice_rows", "table"),
                port("validation_status", "status"),
            ],
            [parameter("validation_rules", "object")],
        ),
        "invoice_status_route_decider": descriptor(
            "invoice_status_route_decider",
            "DomainAdapter",
            "Creates invoice route decisions for valid posting and invalid exception handling.",
            [
                port("valid_invoice_rows", "table"),
                port("invalid_invoice_rows", "table"),
                port("validation_status", "status"),
            ],
            [port("route_decision", "json"), port("routing_status", "status")],
            [parameter("valid_route"), parameter("invalid_route")],
        ),
        "erp_invoice_posting_client": descriptor(
            "erp_invoice_posting_client",
            "Publisher",
            "Posts validated invoice rows to a configured ERP API endpoint.",
            [port("valid_invoice_rows", "table"), port("erp_api", "object", channel="external_resource")],
            [port("posting_status", "status")],
            [parameter("posting_endpoint")],
            network="required",
            secret="optional",
        ),
        "exception_case_creator": descriptor(
            "exception_case_creator",
            "Publisher",
            "Creates exception-tracker cases for invalid invoice records.",
            [
                port("invalid_invoice_rows", "table"),
                port("exception_tracker", "object", channel="external_resource"),
            ],
            [port("exception_case_records", "json"), port("exception_status", "status")],
            [parameter("case_type")],
            network="required",
            secret="optional",
        ),
        "sales_warehouse_global_extract": descriptor(
            "sales_warehouse_global_extract",
            "Extractor",
            "Extracts global sales data from a configured sales warehouse.",
            [port("sales_warehouse", "object", channel="external_resource")],
            [port("global_sales_extract", "table"), port("extraction_status", "status")],
            [parameter("query_name")],
            network="required",
            secret="optional",
        ),
        "regional_sales_dashboard_publisher": descriptor(
            "regional_sales_dashboard_publisher",
            "Publisher",
            "Publishes regional sales aggregates to a configured dashboard service.",
            [
                port("global_sales_extract", "table"),
                port("dashboard_service", "object", channel="external_resource"),
            ],
            [port("dashboard_payload", "json"), port("publication_status", "status")],
            [parameter("region"), parameter("aggregation_level")],
            network="required",
            secret="optional",
        ),
    }
    for service_id, document in services.items():
        dump_yaml(target / "services" / f"{service_id}.yaml", document)

    entries = []
    for path in sorted((target / "services").glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        entries.append(
            {
                "service_id": document["service_id"],
                "version": document["version"],
                "category": document["category"],
                "descriptor_path": f"services/{path.name}",
                "sha256": base.sha256(path),
            }
        )
    dump_yaml(
        target / "catalog.yaml",
        {
            "catalog_id": "serviceflow_catalog",
            "version": CATALOG_VERSION,
            "created_at": CREATED_AT,
            "descriptor_schema": "schemas/service_descriptor.schema.json",
            "generation": {
                "run_id": "curated-validation-batch-02",
                "model": "manual-curation",
                "splits": ["validation"],
                "base_snapshot": BASE_CATALOG_VERSION,
            },
            "service_count": len(entries),
            "services": entries,
        },
    )


def candidates(
    pipeline: str, bindings: list[dict[str, Any]], intents: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    distractors = [
        "reviewed_domain_adapter",
        "temporary_resource_cleanup",
        "csv_to_structured_json_standardizer",
        "tabular_dataset_database_loader",
        "http_json_request_extractor",
        "report_artifact_object_storage_archiver",
        "bi_dashboard_refresh_trigger",
        "file_location_availability_sensor",
    ]
    refs_by_service: dict[str, list[str]] = defaultdict(list)
    intent_index = {item["intent_id"]: item for item in intents}
    for binding in bindings:
        refs = refs_by_service[binding["service_id"]]
        for ref in intent_index[binding["intent_id"]]["source_step_refs"]:
            if ref not in refs:
                refs.append(ref)

    public, private, review_sets = [], [], []
    for number, service_id in enumerate(refs_by_service):
        options = [service_id, distractors[number % len(distractors)], distractors[(number + 1) % len(distractors)]]
        options = list(dict.fromkeys(options))
        while len(options) < 3:
            options.append("reviewed_domain_adapter")
            options = list(dict.fromkeys(options))
        set_id = f"validation_{pipeline}_{service_id}_candidates"
        refs = refs_by_service[service_id]
        public.append({"candidate_set_id": set_id, "source_step_refs": refs, "service_ids": options})
        private.append(
            {
                "candidate_set_id": set_id,
                "required_service_id": service_id,
                "labels": {
                    options[0]: "gold",
                    options[1]: "semantic_mismatch",
                    options[2]: "generic_escape_hatch",
                },
            }
        )
        review_sets.append(
            {
                "candidate_set_id": set_id,
                "required_service_id": service_id,
                "source_step_refs": refs,
                "candidates": [
                    {"service_id": options[0], "label": "gold", "rationale": "Reviewed contract match."},
                    {
                        "service_id": options[1],
                        "label": "semantic_mismatch",
                        "rationale": "Capability overlap without the required service contract.",
                    },
                    {
                        "service_id": options[2],
                        "label": "generic_escape_hatch",
                        "rationale": "Generic alternative is less specific than the reviewed service.",
                    },
                ],
            }
        )
    return (
        {
            "candidate_set_version": "0.1.0",
            "benchmark_id": f"validation:{pipeline}",
            "catalog_snapshot": {"catalog_id": "serviceflow_catalog", "version": CATALOG_VERSION},
            "candidate_sets": public,
        },
        {
            "candidate_label_version": "0.1.0",
            "benchmark_id": f"validation:{pipeline}",
            "candidate_sets": private,
        },
        {
            "pipeline_id": pipeline,
            "candidate_sets": review_sets,
            "new_distractor_services": [],
            "review_notes": [
                "Curated for Validation-20 batch 02; labels are private benchmark gold.",
                "Repeated-service candidate sets aggregate all source steps bound to that service.",
            ],
        },
    )


def write_instance(
    flow: dict[str, Any], task_outputs: dict[str, list[str]], fixture: dict[str, Any]
) -> dict[str, Any]:
    pipeline = flow["source"]["pipeline_id"]
    root = ROOT / "benchmark/instances/validation" / pipeline
    dump_yaml(root / "gold/serviceflow.yaml", flow)
    public, private, review = candidates(pipeline, flow["bindings"], flow["service_intents"])
    dump_yaml(root / "candidates/candidate_sets.yaml", public)
    dump_yaml(root / "gold/candidate_labels.yaml", private)
    dump_yaml(
        root / "gold/bindings.yaml",
        {
            "binding_gold_version": "0.1.0",
            "benchmark_id": flow["source"]["benchmark_id"],
            "bindings": [
                {key: item[key] for key in ["intent_id", "service_id", "service_version"]}
                for item in flow["bindings"]
            ],
        },
    )
    dump_yaml(
        root / "gold/artifact_mappings.yaml",
        {
            "artifact_mapping_version": "0.1.0",
            "benchmark_id": flow["source"]["benchmark_id"],
            "mappings": [
                {
                    "intent_id": item["intent_id"],
                    "inputs": {x["port"]: x["artifact_id"] for x in item["input_bindings"]},
                    "outputs": {x["port"]: x["artifact_id"] for x in item["output_bindings"]},
                }
                for item in flow["bindings"]
            ],
        },
    )

    tasks = []
    for number, item in enumerate(flow["service_intents"], start=1):
        task_id = item["intent_id"]
        filename = f"{number:02d}_{task_id}.py"
        (root / "runtime/scripts" / filename).write_text(
            base.mock_script(task_id, task_outputs[task_id]), encoding="utf-8"
        )
        predecessors = [edge["from"] for edge in flow["control_flow"]["edges"] if edge["to"] == task_id]
        task = {
            "intent_id": task_id,
            "script": f"scripts/{filename}",
            "arguments": ["--workspace", "{workspace}", "--fixture", "{fixtures}/fixture.json"],
        }
        if predecessors:
            task["dependencies"] = predecessors
        tasks.append(task)

    manifest = {
        "runtime_manifest_version": "0.1.0",
        "pipeline_id": pipeline,
        "image": "python:3.12-slim",
        "workflow_parameters": [],
        "tasks": tasks,
        "scenarios": [{"name": "nominal", "parameters": {}}],
    }
    if flow["schedule"]["type"] == "cron":
        manifest["cron"] = {"schedule": flow["schedule"]["expression"], "timezone": "UTC"}
    dump_yaml(root / "runtime/manifest.yaml", manifest)
    (root / "fixtures/inputs/fixture.json").write_text(
        json.dumps(fixture, indent=2) + "\n", encoding="utf-8"
    )
    final_status = task_outputs[flow["service_intents"][-1]["intent_id"]][-1]
    dump_yaml(
        root / "gold/assertions.yaml",
        {
            "assertions_version": "0.1.0",
            "pipeline_id": pipeline,
            "scenarios": [
                {
                    "scenario": "nominal",
                    "assertions": [
                        {
                            "assertion_id": "final_status_succeeds",
                            "type": "json_path_equals",
                            "path": f"artifacts/{final_status}.json",
                            "json_path": "success",
                            "expected": True,
                        }
                    ],
                }
            ],
        },
    )
    (root / "README.md").write_text(
        f"# {pipeline}\n\n"
        "Validation-20 batch 02. Source evidence is low-information; service bindings are "
        "explicitly marked strongly inferred. The runtime uses deterministic, task-specific "
        "mock scripts and does not claim external-system execution.\n",
        encoding="utf-8",
    )
    write_resources(root)
    return review


def build_flow(
    pipeline: str,
    purpose: str,
    topology: str,
    systems: list[dict[str, Any]],
    rows: list[tuple[Any, ...]],
    seed_artifacts: dict[str, tuple[str, str | None, str | None]],
    edges: list[tuple[str, str]],
    *,
    parallel_groups: list[list[str]] | None = None,
    branches: list[dict[str, Any]] | None = None,
    gates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    intents = [base.intent(a, b, c, d, e, f) for a, b, c, d, e, f, *_ in rows]
    bindings = [base.binding(a, g, h, i, j) for a, _, _, _, _, _, g, h, i, j in rows]
    artifacts = [
        base.artifact(key, typ, producer, [], external=external)
        for key, (typ, producer, external) in seed_artifacts.items()
    ]
    for row in rows:
        intent_id, _category, _source_step, _inputs, outputs, _systems, service_id, _input_map, output_map, _params = row
        document = yaml.safe_load(
            (
                ROOT
                / "benchmark/catalog/snapshots"
                / CATALOG_VERSION
                / "services"
                / f"{service_id}.yaml"
            ).read_text(encoding="utf-8")
        )
        for output in outputs:
            port_name = next(port for port, artifact_id in output_map.items() if artifact_id == output)
            data_type = next(
                item["data_type"]
                for item in document["interface"]["outputs"]
                if item["name"] == port_name
            )
            consumers = [other[0] for other in rows if output in other[3]]
            artifacts.append(
                base.artifact(
                    output,
                    data_type,
                    intent_id,
                    consumers,
                    role="output" if not consumers else "intermediate",
                )
            )
    flow = base.serviceflow(pipeline, purpose, topology, systems, intents, artifacts, bindings, edges, True)
    flow["control_flow"]["parallel_groups"] = parallel_groups or []
    flow["control_flow"]["branches"] = branches or []
    flow["control_flow"]["gates"] = gates or []
    return flow


def main() -> None:
    prepare_catalogue()
    reviews = []

    definitions = [
        (
            "val_customer_profile_refresh",
            "Refresh customer profiles by extracting CRM records, normalizing fields, deduplicating rows, loading a profile table, and emitting a refresh summary.",
            "linear",
            base.systems([("crm_api", "http_api", "CRM API"), ("customer_warehouse", "database", "Customer warehouse")]),
            [
                ("extract_crm_records", "Extractor", "extract_crm_records", ["crm_api_resource"], ["crm_records", "crm_extraction_status"], ["crm_api"], "crm_api_record_extractor", {"crm_api": "crm_api_resource"}, {"crm_records": "crm_records", "extraction_status": "crm_extraction_status"}, {"object_name": "customers", "updated_since": "scheduled_interval_start"}),
                ("normalize_profile_fields", "Transformer", "normalize_profile_fields", ["crm_records"], ["normalized_profiles", "normalization_status"], [], "customer_profile_field_normalizer", {"crm_records": "crm_records"}, {"normalized_profiles": "normalized_profiles", "normalization_status": "normalization_status"}, {"normalization_profile": {"email": "lowercase", "phone": "e164"}}),
                ("deduplicate_customers", "Reconciler", "deduplicate_customers", ["normalized_profiles"], ["deduplicated_profiles", "dedup_status"], [], "customer_profile_deduplicator", {"normalized_profiles": "normalized_profiles"}, {"deduplicated_profiles": "deduplicated_profiles", "dedup_status": "dedup_status"}, {"identity_keys": ["email", "crm_id"], "survivorship_policy": "latest_updated_at"}),
                ("load_profile_table", "Loader", "load_profile_table", ["deduplicated_profiles", "customer_warehouse_resource"], ["profile_table", "profile_load_status"], ["customer_warehouse"], "customer_profile_table_loader", {"deduplicated_profiles": "deduplicated_profiles", "customer_warehouse": "customer_warehouse_resource"}, {"profile_table": "profile_table", "load_status": "profile_load_status"}, {"target_table": "customer_profile", "write_mode": "upsert"}),
                ("emit_refresh_summary", "ReportGenerator", "emit_refresh_summary", ["profile_table"], ["refresh_summary", "summary_status"], [], "profile_refresh_summary_emitter", {"profile_table": "profile_table"}, {"refresh_summary": "refresh_summary", "summary_status": "summary_status"}, {"summary_name": "customer_profile_refresh"}),
            ],
            {"crm_api_resource": ("object", None, "crm_api"), "customer_warehouse_resource": ("object", None, "customer_warehouse")},
            [
                ("extract_crm_records", "normalize_profile_fields"),
                ("normalize_profile_fields", "deduplicate_customers"),
                ("deduplicate_customers", "load_profile_table"),
                ("load_profile_table", "emit_refresh_summary"),
            ],
            {},
            {},
            {"crm_records": 3, "deduplicated_profiles": 2},
        ),
        (
            "val_parallel_thumbnail_generation",
            "Download new product images and generate small, medium, and large thumbnail bundles in parallel.",
            "fan_out",
            base.systems([("image_cdn", "http_api", "Image CDN"), ("object_storage", "object_storage", "Object storage")]),
            [
                ("download_new_images", "Extractor", "download_new_images", ["image_cdn_resource"], ["raw_product_images", "download_status"], ["image_cdn"], "image_cdn_batch_downloader", {"image_cdn": "image_cdn_resource"}, {"raw_product_images": "raw_product_images", "download_status": "download_status"}, {"prefix": "/products/new", "max_images": 50}),
                ("generate_small_thumbnail", "Transformer", "generate_small_thumbnail", ["raw_product_images"], ["small_thumbnail", "small_render_status"], [], "image_thumbnail_renderer", {"raw_product_images": "raw_product_images"}, {"thumbnail_bundle": "small_thumbnail", "render_status": "small_render_status"}, {"size_label": "small", "width": 160, "height": 160}),
                ("generate_medium_thumbnail", "Transformer", "generate_medium_thumbnail", ["raw_product_images"], ["medium_thumbnail", "medium_render_status"], [], "image_thumbnail_renderer", {"raw_product_images": "raw_product_images"}, {"thumbnail_bundle": "medium_thumbnail", "render_status": "medium_render_status"}, {"size_label": "medium", "width": 512, "height": 512}),
                ("generate_large_thumbnail", "Transformer", "generate_large_thumbnail", ["raw_product_images"], ["large_thumbnail", "large_render_status"], [], "image_thumbnail_renderer", {"raw_product_images": "raw_product_images"}, {"thumbnail_bundle": "large_thumbnail", "render_status": "large_render_status"}, {"size_label": "large", "width": 1024, "height": 1024}),
            ],
            {"image_cdn_resource": ("object", None, "image_cdn"), "object_storage_resource": ("object", None, "object_storage")},
            [
                ("download_new_images", "generate_small_thumbnail"),
                ("download_new_images", "generate_medium_thumbnail"),
                ("download_new_images", "generate_large_thumbnail"),
            ],
            [
                {
                    "group_id": "thumbnail_fanout",
                    "intent_ids": [
                        "generate_small_thumbnail",
                        "generate_medium_thumbnail",
                        "generate_large_thumbnail",
                    ],
                }
            ],
            {},
            {"images": ["sku-1.jpg", "sku-2.jpg"]},
        ),
        (
            "val_file_arrival_ingest_gate",
            "Wait for an expected partner file, validate its checksum, and load the verified file into staging.",
            "sensor_gated",
            base.systems([("partner_sftp", "sftp", "Partner SFTP"), ("staging_database", "database", "Staging database")]),
            [
                ("wait_for_partner_file", "Sensor", "wait_for_partner_file", ["partner_sftp_resource"], ["partner_file_available", "availability_status"], ["partner_sftp"], "file_location_availability_sensor", {"file_location_resource": "partner_sftp_resource"}, {"availability_decision": "partner_file_available", "check_status": "availability_status"}, {"location_type": "sftp", "path": "/incoming", "availability_condition": "partner_file_exists", "filename_pattern": "partner_file.csv"}),
                ("validate_file_checksum", "QualityCheck", "validate_file_checksum", ["partner_file_csv", "checksum_record"], ["verified_partner_file", "checksum_status"], [], "partner_file_checksum_validator", {"partner_file": "partner_file_csv", "checksum_record": "checksum_record"}, {"verified_partner_file": "verified_partner_file", "checksum_status": "checksum_status"}, {"algorithm": "sha256"}),
                ("load_file_to_staging", "Loader", "load_file_to_staging", ["verified_partner_file", "staging_database_resource"], ["staging_table", "staging_load_status"], ["staging_database"], "database_csv_snapshot_importer", {"csv_snapshot": "verified_partner_file", "target_database": "staging_database_resource"}, {"target_database_reference": "staging_table", "load_status": "staging_load_status"}, {"import_spec": {"target_table": "partner_staging"}, "load_mode": "replace", "target_label": "staging"}),
            ],
            {"partner_sftp_resource": ("object", None, "partner_sftp"), "partner_file_csv": ("csv", None, None), "checksum_record": ("object", None, None), "staging_database_resource": ("object", None, "staging_database")},
            [("wait_for_partner_file", "validate_file_checksum"), ("validate_file_checksum", "load_file_to_staging")],
            {},
            {
                "gate_id": "partner_file_arrival_gate",
                "sensor_intent": "wait_for_partner_file",
                "condition": "partner_file_exists == true",
                "gated_intents": ["validate_file_checksum", "load_file_to_staging"],
            },
            {"filename": "partner_file.csv", "checksum": "sha256:example"},
        ),
        (
            "val_invoice_exception_router",
            "Validate invoices, route valid invoices to ERP posting, and route invalid invoices to exception handling.",
            "branch_merge",
            base.systems([("erp_api", "http_api", "ERP API"), ("exception_tracker", "http_api", "Exception tracker")]),
            [
                ("validate_invoices", "QualityCheck", "validate_invoices", ["invoice_batch"], ["valid_invoice_rows", "invalid_invoice_rows", "invoice_validation_status"], [], "invoice_batch_validator", {"invoice_batch": "invoice_batch"}, {"valid_invoice_rows": "valid_invoice_rows", "invalid_invoice_rows": "invalid_invoice_rows", "validation_status": "invoice_validation_status"}, {"validation_rules": {"required": ["invoice_id", "amount", "vendor_id"]}}),
                ("route_invoice_status", "DomainAdapter", "route_invoice_status", ["valid_invoice_rows", "invalid_invoice_rows", "invoice_validation_status"], ["invoice_route_decision", "invoice_routing_status"], [], "invoice_status_route_decider", {"valid_invoice_rows": "valid_invoice_rows", "invalid_invoice_rows": "invalid_invoice_rows", "validation_status": "invoice_validation_status"}, {"route_decision": "invoice_route_decision", "routing_status": "invoice_routing_status"}, {"valid_route": "post_valid_invoices", "invalid_route": "create_exception_cases"}),
                ("post_valid_invoices", "Publisher", "post_valid_invoices", ["valid_invoice_rows", "erp_api_resource"], ["posting_status"], ["erp_api"], "erp_invoice_posting_client", {"valid_invoice_rows": "valid_invoice_rows", "erp_api": "erp_api_resource"}, {"posting_status": "posting_status"}, {"posting_endpoint": "/invoices/post"}),
                ("create_exception_cases", "Publisher", "create_exception_cases", ["invalid_invoice_rows", "exception_tracker_resource"], ["exception_case_records", "exception_status"], ["exception_tracker"], "exception_case_creator", {"invalid_invoice_rows": "invalid_invoice_rows", "exception_tracker": "exception_tracker_resource"}, {"exception_case_records": "exception_case_records", "exception_status": "exception_status"}, {"case_type": "invoice_validation_exception"}),
            ],
            {"invoice_batch": ("table", None, None), "erp_api_resource": ("object", None, "erp_api"), "exception_tracker_resource": ("object", None, "exception_tracker")},
            [
                ("validate_invoices", "route_invoice_status"),
                ("route_invoice_status", "post_valid_invoices"),
                ("route_invoice_status", "create_exception_cases"),
            ],
            {},
            {
                "branch_id": "invoice_exception_route",
                "decision_intent": "route_invoice_status",
                "decision_artifact": "invoice_route_decision",
                "cases": [
                    {
                        "case_id": "valid",
                        "condition": "invoice_route_decision.route == valid",
                        "next_intents": ["post_valid_invoices"],
                    },
                    {
                        "case_id": "invalid",
                        "condition": "invoice_route_decision.route == invalid",
                        "next_intents": ["create_exception_cases"],
                    },
                ],
            },
            {"invoice_count": 4, "invalid_count": 1},
        ),
        (
            "val_region_sales_fanout",
            "Extract global sales data and publish regional aggregates for North America, Europe, and APAC in parallel.",
            "fan_out",
            base.systems([("sales_warehouse", "database", "Sales warehouse"), ("dashboard_service", "http_api", "Regional dashboard service")]),
            [
                ("extract_global_sales", "Extractor", "extract_global_sales", ["sales_warehouse_resource"], ["global_sales_extract", "sales_extract_status"], ["sales_warehouse"], "sales_warehouse_global_extract", {"sales_warehouse": "sales_warehouse_resource"}, {"global_sales_extract": "global_sales_extract", "extraction_status": "sales_extract_status"}, {"query_name": "global_sales_daily"}),
                ("publish_na_sales", "Publisher", "publish_na_sales", ["global_sales_extract", "dashboard_service_resource"], ["na_dashboard_payload", "na_publication_status"], ["dashboard_service"], "regional_sales_dashboard_publisher", {"global_sales_extract": "global_sales_extract", "dashboard_service": "dashboard_service_resource"}, {"dashboard_payload": "na_dashboard_payload", "publication_status": "na_publication_status"}, {"region": "NA", "aggregation_level": "region"}),
                ("publish_eu_sales", "Publisher", "publish_eu_sales", ["global_sales_extract", "dashboard_service_resource"], ["eu_dashboard_payload", "eu_publication_status"], ["dashboard_service"], "regional_sales_dashboard_publisher", {"global_sales_extract": "global_sales_extract", "dashboard_service": "dashboard_service_resource"}, {"dashboard_payload": "eu_dashboard_payload", "publication_status": "eu_publication_status"}, {"region": "EU", "aggregation_level": "region"}),
                ("publish_apac_sales", "Publisher", "publish_apac_sales", ["global_sales_extract", "dashboard_service_resource"], ["apac_dashboard_payload", "apac_publication_status"], ["dashboard_service"], "regional_sales_dashboard_publisher", {"global_sales_extract": "global_sales_extract", "dashboard_service": "dashboard_service_resource"}, {"dashboard_payload": "apac_dashboard_payload", "publication_status": "apac_publication_status"}, {"region": "APAC", "aggregation_level": "region"}),
            ],
            {"sales_warehouse_resource": ("object", None, "sales_warehouse"), "dashboard_service_resource": ("object", None, "dashboard_service")},
            [
                ("extract_global_sales", "publish_na_sales"),
                ("extract_global_sales", "publish_eu_sales"),
                ("extract_global_sales", "publish_apac_sales"),
            ],
            [
                {
                    "group_id": "regional_sales_fanout",
                    "intent_ids": ["publish_na_sales", "publish_eu_sales", "publish_apac_sales"],
                }
            ],
            {},
            {"regions": ["NA", "EU", "APAC"]},
        ),
    ]

    for pipeline, purpose, topology, systems, rows, seed_artifacts, edges, parallel, control, fixture in definitions:
        flow = build_flow(
            pipeline,
            purpose,
            topology,
            systems,
            rows,
            seed_artifacts,
            edges,
            parallel_groups=parallel if isinstance(parallel, list) else None,
            branches=[control] if topology == "branch_merge" and control else None,
            gates=[control] if topology == "sensor_gated" and control else None,
        )
        task_outputs = {item["intent_id"]: item["outputs"] for item in flow["service_intents"]}
        reviews.append(write_instance(flow, task_outputs, fixture))

    review_dir = ROOT / "benchmark/catalog/review" / CATALOG_VERSION
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "candidate_relationships.private.json").write_text(
        json.dumps({"catalog_version": CATALOG_VERSION, "pipelines": reviews}, indent=2) + "\n",
        encoding="utf-8",
    )
    print("authored validation batch 02: 5 instances and catalogue 0.2.1")


if __name__ == "__main__":
    main()
