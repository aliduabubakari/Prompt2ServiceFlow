#!/usr/bin/env python3
"""Author Validation-20 batch 03 as a reviewed benchmark slice."""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import author_validation_batch_01 as base
import author_validation_batch_02 as helpers
import yaml

from prompt2serviceflow.compiler.argo import write_resources


ROOT = Path(__file__).resolve().parents[1]
CATALOG_VERSION = "0.2.2"
BASE_CATALOG_VERSION = "0.2.1"
CREATED_AT = "2026-06-25T00:00:00+00:00"

base.CATALOG_VERSION = CATALOG_VERSION
base.CREATED_AT = CREATED_AT
helpers.CATALOG_VERSION = CATALOG_VERSION
helpers.CREATED_AT = CREATED_AT


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
    document["invocation"]["image"] = "prompt2serviceflow/runtime:0.2.2"
    document["capability"]["keywords"] = list(dict.fromkeys(document["capability"]["keywords"]))
    document["provenance"]["created_at"] = CREATED_AT
    document["provenance"]["source_refs"] = ["validation-batch-03:curated-extension"]
    document["provenance"]["notes"] = [
        "Curated from sparse Validation-20 batch 03 descriptions; bindings retain inference confidence."
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
        "iot_broker_sensor_feed_collector": descriptor(
            "iot_broker_sensor_feed_collector",
            "Extractor",
            "Collects one configured industrial IoT sensor feed from a bound broker.",
            [port("iot_broker", "object", channel="external_resource")],
            [port("sensor_feed", "table"), port("collection_status", "status")],
            [parameter("feed_type"), parameter("window_minutes", "integer")],
            network="required",
            secret="optional",
        ),
        "sensor_window_alignment_fuser": descriptor(
            "sensor_window_alignment_fuser",
            "Integrator",
            "Aligns temperature, vibration, and pressure feeds into timestamp windows.",
            [port("temperature_feed", "table"), port("vibration_feed", "table"), port("pressure_feed", "table")],
            [port("aligned_sensor_windows", "table"), port("alignment_status", "status")],
            [parameter("timestamp_column"), parameter("window_seconds", "integer")],
        ),
        "iot_anomaly_feature_calculator": descriptor(
            "iot_anomaly_feature_calculator",
            "Transformer",
            "Computes anomaly features from aligned industrial sensor windows.",
            [port("aligned_sensor_windows", "table")],
            [port("anomaly_features", "table"), port("feature_status", "status")],
            [parameter("feature_profile", "object")],
        ),
        "timeseries_fused_dataset_writer": descriptor(
            "timeseries_fused_dataset_writer",
            "Loader",
            "Writes fused anomaly features to a configured time-series database.",
            [port("anomaly_features", "table"), port("timeseries_database", "object", channel="external_resource")],
            [port("fused_dataset_reference", "object"), port("write_status", "status")],
            [parameter("measurement_name"), parameter("write_mode")],
            network="required",
            secret="optional",
        ),
        "claims_database_batch_extractor": descriptor(
            "claims_database_batch_extractor",
            "Extractor",
            "Extracts an insurance claim batch from a configured claims database.",
            [port("claims_database", "object", channel="external_resource")],
            [port("claim_batch", "table"), port("extraction_status", "status")],
            [parameter("claim_query")],
            network="required",
            secret="optional",
        ),
        "claim_risk_scoring_service": descriptor(
            "claim_risk_scoring_service",
            "ScoringService",
            "Scores insurance claims for adjudication risk using a configured profile.",
            [port("claim_batch", "table"), port("risk_service", "object", channel="external_resource")],
            [port("risk_scores", "table"), port("scoring_status", "status")],
            [parameter("risk_profile")],
            network="required",
            secret="optional",
        ),
        "claim_risk_route_decider": descriptor(
            "claim_risk_route_decider",
            "DomainAdapter",
            "Routes claim risk scores to manual adjudication or auto approval.",
            [port("risk_scores", "table")],
            [port("claim_route_decision", "json"), port("routing_status", "status")],
            [parameter("risk_threshold", "number"), parameter("manual_route"), parameter("auto_route")],
        ),
        "manual_claim_adjudication_recorder": descriptor(
            "manual_claim_adjudication_recorder",
            "DomainAdapter",
            "Records high-risk claims for manual adjudication review.",
            [port("risk_scores", "table")],
            [port("manual_adjudication_records", "json"), port("manual_status", "status")],
            [parameter("queue_name")],
        ),
        "low_risk_claim_auto_approver": descriptor(
            "low_risk_claim_auto_approver",
            "DomainAdapter",
            "Auto-approves low-risk claims under a configured adjudication threshold.",
            [port("risk_scores", "table")],
            [port("auto_approval_records", "json"), port("approval_status", "status")],
            [parameter("approval_policy")],
        ),
        "claim_settlement_summary_writer": descriptor(
            "claim_settlement_summary_writer",
            "ReportGenerator",
            "Writes a settlement summary after manual and auto-adjudication paths complete.",
            [port("manual_adjudication_records", "json"), port("auto_approval_records", "json")],
            [port("settlement_summary", "json"), port("summary_status", "status")],
            [parameter("summary_name")],
        ),
        "marketing_event_api_extractor": descriptor(
            "marketing_event_api_extractor",
            "Extractor",
            "Extracts one configured marketing event stream from an advertising API.",
            [port("ad_platform_api", "object", channel="external_resource")],
            [port("marketing_events", "table"), port("extraction_status", "status")],
            [parameter("event_type"), parameter("lookback_days", "integer")],
            network="required",
            secret="optional",
        ),
        "commerce_purchase_event_extractor": descriptor(
            "commerce_purchase_event_extractor",
            "Extractor",
            "Extracts purchase events from a commerce database for attribution analysis.",
            [port("commerce_database", "object", channel="external_resource")],
            [port("purchase_events", "table"), port("extraction_status", "status")],
            [parameter("purchase_query")],
            network="required",
            secret="optional",
        ),
        "customer_event_attribution_joiner": descriptor(
            "customer_event_attribution_joiner",
            "Integrator",
            "Joins impressions, clicks, and purchases into customer-level event paths.",
            [port("impressions", "table"), port("clicks", "table"), port("purchases", "table")],
            [port("joined_customer_events", "table"), port("join_status", "status")],
            [parameter("identity_key"), parameter("attribution_window_days", "integer")],
        ),
        "attribution_metric_calculator": descriptor(
            "attribution_metric_calculator",
            "Aggregator",
            "Computes marketing attribution metrics from joined customer events.",
            [port("joined_customer_events", "table")],
            [port("attribution_metrics", "table"), port("calculation_status", "status")],
            [parameter("model_name"), parameter("conversion_event")],
        ),
        "attribution_table_publisher": descriptor(
            "attribution_table_publisher",
            "Publisher",
            "Publishes attribution metrics to a durable analytics table.",
            [port("attribution_metrics", "table"), port("commerce_database", "object", channel="external_resource")],
            [port("attribution_table", "table"), port("publication_status", "status")],
            [parameter("target_table"), parameter("write_mode")],
            network="required",
            secret="optional",
        ),
        "campaign_summary_notification_sender": descriptor(
            "campaign_summary_notification_sender",
            "Notifier",
            "Sends a campaign attribution summary through a configured email service.",
            [port("attribution_table", "table"), port("email_service", "object", channel="external_resource")],
            [port("campaign_notification_status", "notification")],
            [parameter("recipient_group"), parameter("subject")],
            network="required",
            secret="optional",
        ),
        "customer_extract_profiler": descriptor(
            "customer_extract_profiler",
            "DataProfiler",
            "Profiles a customer extract before quality-rule evaluation.",
            [port("customer_extract", "table")],
            [port("profile_report", "json"), port("profile_status", "status")],
            [parameter("profile_rules", "object")],
        ),
        "customer_quality_rule_evaluator": descriptor(
            "customer_quality_rule_evaluator",
            "QualityCheck",
            "Evaluates customer profile quality rules and separates valid and invalid records.",
            [port("profile_report", "json"), port("customer_extract", "table")],
            [port("valid_records", "table"), port("invalid_records", "table"), port("quality_decision", "json"), port("quality_status", "status")],
            [parameter("quality_rules", "object")],
        ),
        "valid_customer_records_loader": descriptor(
            "valid_customer_records_loader",
            "Loader",
            "Loads quality-approved customer records into the customer warehouse.",
            [port("valid_records", "table"), port("customer_warehouse", "object", channel="external_resource")],
            [port("valid_load_status", "status")],
            [parameter("target_table"), parameter("write_mode")],
            network="required",
            secret="optional",
        ),
        "invalid_customer_records_quarantine_publisher": descriptor(
            "invalid_customer_records_quarantine_publisher",
            "Publisher",
            "Publishes invalid customer records to a configured quarantine bucket.",
            [port("invalid_records", "table"), port("quarantine_bucket", "object", channel="external_resource")],
            [port("quarantine_reference", "object"), port("quarantine_status", "status")],
            [parameter("quarantine_prefix")],
            network="required",
            secret="optional",
        ),
        "quality_audit_summary_writer": descriptor(
            "quality_audit_summary_writer",
            "ReportGenerator",
            "Writes a quality audit summary after load and quarantine paths complete.",
            [port("valid_load_status", "status"), port("quarantine_status", "status")],
            [port("quality_audit", "json"), port("audit_status", "status")],
            [parameter("audit_name")],
        ),
        "event_lake_raw_event_extractor": descriptor(
            "event_lake_raw_event_extractor",
            "Extractor",
            "Extracts raw model-feature events from an event lake.",
            [port("event_lake", "object", channel="external_resource")],
            [port("raw_events", "table"), port("extraction_status", "status")],
            [parameter("event_path"), parameter("lookback_hours", "integer")],
            network="required",
            secret="optional",
        ),
        "event_record_cleaner": descriptor(
            "event_record_cleaner",
            "Transformer",
            "Cleans raw event records for downstream feature aggregation.",
            [port("raw_events", "table")],
            [port("clean_events", "table"), port("cleaning_status", "status")],
            [parameter("cleaning_rules", "object")],
        ),
        "user_feature_aggregator": descriptor(
            "user_feature_aggregator",
            "Aggregator",
            "Aggregates cleaned event records into a user feature table.",
            [port("clean_events", "table")],
            [port("feature_table", "table"), port("aggregation_status", "status")],
            [parameter("feature_spec", "object")],
        ),
        "feature_drift_statistics_computer": descriptor(
            "feature_drift_statistics_computer",
            "DataProfiler",
            "Computes feature drift statistics for a refreshed feature table.",
            [port("feature_table", "table")],
            [port("drift_report", "json"), port("drift_status", "status")],
            [parameter("baseline_window"), parameter("drift_metrics", "array")],
        ),
        "feature_table_drift_validator": descriptor(
            "feature_table_drift_validator",
            "QualityCheck",
            "Validates a refreshed feature table against drift statistics.",
            [port("feature_table", "table"), port("drift_report", "json")],
            [port("validated_feature_table", "table"), port("validation_status", "status")],
            [parameter("drift_thresholds", "object")],
        ),
        "feature_store_table_publisher": descriptor(
            "feature_store_table_publisher",
            "Publisher",
            "Publishes a validated feature table to a bound feature store.",
            [port("validated_feature_table", "table"), port("feature_store", "object", channel="external_resource")],
            [port("feature_publication_status", "status")],
            [parameter("feature_table_name"), parameter("write_mode")],
            network="required",
            secret="optional",
        ),
        "model_team_notification_sender": descriptor(
            "model_team_notification_sender",
            "Notifier",
            "Sends feature-refresh completion status to a configured model team notification service.",
            [port("feature_publication_status", "status"), port("notification_service", "object", channel="external_resource")],
            [port("model_team_notification_status", "notification")],
            [parameter("recipient_group"), parameter("message_template")],
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
                "run_id": "curated-validation-batch-03",
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
        "bi_dashboard_refresh_trigger",
        "bulk_email_campaign_sender",
        "parquet_tabular_data_profiler",
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
                    {"service_id": options[1], "label": "semantic_mismatch", "rationale": "Capability overlap without the required service contract."},
                    {"service_id": options[2], "label": "generic_escape_hatch", "rationale": "Generic alternative is less specific than the reviewed service."},
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
        {"candidate_label_version": "0.1.0", "benchmark_id": f"validation:{pipeline}", "candidate_sets": private},
        {
            "pipeline_id": pipeline,
            "candidate_sets": review_sets,
            "new_distractor_services": [],
            "review_notes": ["Curated for Validation-20 batch 03; labels are private benchmark gold."],
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
        task = {"intent_id": task_id, "script": f"scripts/{filename}", "arguments": ["--workspace", "{workspace}", "--fixture", "{fixtures}/fixture.json"]}
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
        "cron": {"schedule": "0 0 * * *", "timezone": "UTC"},
    }
    dump_yaml(root / "runtime/manifest.yaml", manifest)
    (root / "fixtures/inputs/fixture.json").write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
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
        "Validation-20 batch 03. Source evidence is low-information; service bindings are "
        "explicitly marked strongly inferred. The runtime uses deterministic, task-specific "
        "mock scripts and does not claim external-system execution.\n",
        encoding="utf-8",
    )
    write_resources(root)
    return review


def build_flow(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return helpers.build_flow(*args, **kwargs)


def main() -> None:
    prepare_catalogue()
    reviews = []
    definitions = [
        (
            "val_iot_sensor_fusion",
            "Collect temperature, vibration, and pressure sensor feeds in parallel, align them by timestamp, compute anomaly features, and write a fused dataset.",
            "fan_out_fan_in",
            base.systems([("iot_broker", "http_api", "IoT broker"), ("timeseries_database", "database", "Time-series database")]),
            [
                ("collect_temperature_feed", "Extractor", "collect_temperature_feed", ["iot_broker_resource"], ["temperature_feed", "temperature_collection_status"], ["iot_broker"], "iot_broker_sensor_feed_collector", {"iot_broker": "iot_broker_resource"}, {"sensor_feed": "temperature_feed", "collection_status": "temperature_collection_status"}, {"feed_type": "temperature", "window_minutes": 60}),
                ("collect_vibration_feed", "Extractor", "collect_vibration_feed", ["iot_broker_resource"], ["vibration_feed", "vibration_collection_status"], ["iot_broker"], "iot_broker_sensor_feed_collector", {"iot_broker": "iot_broker_resource"}, {"sensor_feed": "vibration_feed", "collection_status": "vibration_collection_status"}, {"feed_type": "vibration", "window_minutes": 60}),
                ("collect_pressure_feed", "Extractor", "collect_pressure_feed", ["iot_broker_resource"], ["pressure_feed", "pressure_collection_status"], ["iot_broker"], "iot_broker_sensor_feed_collector", {"iot_broker": "iot_broker_resource"}, {"sensor_feed": "pressure_feed", "collection_status": "pressure_collection_status"}, {"feed_type": "pressure", "window_minutes": 60}),
                ("align_sensor_windows", "Integrator", "align_sensor_windows", ["temperature_feed", "vibration_feed", "pressure_feed"], ["aligned_sensor_windows", "alignment_status"], [], "sensor_window_alignment_fuser", {"temperature_feed": "temperature_feed", "vibration_feed": "vibration_feed", "pressure_feed": "pressure_feed"}, {"aligned_sensor_windows": "aligned_sensor_windows", "alignment_status": "alignment_status"}, {"timestamp_column": "event_ts", "window_seconds": 60}),
                ("compute_anomaly_features", "Transformer", "compute_anomaly_features", ["aligned_sensor_windows"], ["anomaly_features", "anomaly_feature_status"], [], "iot_anomaly_feature_calculator", {"aligned_sensor_windows": "aligned_sensor_windows"}, {"anomaly_features": "anomaly_features", "feature_status": "anomaly_feature_status"}, {"feature_profile": {"rolling_window": 5}}),
                ("write_fused_dataset", "Loader", "write_fused_dataset", ["anomaly_features", "timeseries_database_resource"], ["fused_dataset_reference", "fused_write_status"], ["timeseries_database"], "timeseries_fused_dataset_writer", {"anomaly_features": "anomaly_features", "timeseries_database": "timeseries_database_resource"}, {"fused_dataset_reference": "fused_dataset_reference", "write_status": "fused_write_status"}, {"measurement_name": "fused_anomalies", "write_mode": "upsert"}),
            ],
            {"iot_broker_resource": ("object", None, "iot_broker"), "timeseries_database_resource": ("object", None, "timeseries_database")},
            [("collect_temperature_feed", "align_sensor_windows"), ("collect_vibration_feed", "align_sensor_windows"), ("collect_pressure_feed", "align_sensor_windows"), ("align_sensor_windows", "compute_anomaly_features"), ("compute_anomaly_features", "write_fused_dataset")],
            [{"group_id": "sensor_feed_collection", "intent_ids": ["collect_temperature_feed", "collect_vibration_feed", "collect_pressure_feed"]}],
            None,
            {"sensors": ["temperature", "vibration", "pressure"]},
        ),
        (
            "val_claims_adjudication_branch",
            "Score insurance claims, route high-risk claims to manual adjudication, auto-approve low-risk claims, and produce a settlement summary.",
            "branch_merge",
            base.systems([("claims_database", "database", "Claims database"), ("risk_scoring_service", "http_api", "Risk scoring service")]),
            [
                ("ingest_claims", "Extractor", "ingest_claims", ["claims_database_resource"], ["claim_batch", "claim_extract_status"], ["claims_database"], "claims_database_batch_extractor", {"claims_database": "claims_database_resource"}, {"claim_batch": "claim_batch", "extraction_status": "claim_extract_status"}, {"claim_query": "daily_open_claims"}),
                ("score_claim_risk", "ScoringService", "score_claim_risk", ["claim_batch", "risk_scoring_service_resource"], ["risk_scores", "risk_scoring_status"], ["risk_scoring_service"], "claim_risk_scoring_service", {"claim_batch": "claim_batch", "risk_service": "risk_scoring_service_resource"}, {"risk_scores": "risk_scores", "scoring_status": "risk_scoring_status"}, {"risk_profile": "standard"}),
                ("route_claim", "DomainAdapter", "route_claim", ["risk_scores"], ["claim_route_decision", "claim_routing_status"], [], "claim_risk_route_decider", {"risk_scores": "risk_scores"}, {"claim_route_decision": "claim_route_decision", "routing_status": "claim_routing_status"}, {"risk_threshold": 0.75, "manual_route": "manual_adjudication", "auto_route": "auto_approve_claim"}),
                ("manual_adjudication", "DomainAdapter", "manual_adjudication", ["risk_scores"], ["manual_adjudication_records", "manual_status"], [], "manual_claim_adjudication_recorder", {"risk_scores": "risk_scores"}, {"manual_adjudication_records": "manual_adjudication_records", "manual_status": "manual_status"}, {"queue_name": "manual_claim_review"}),
                ("auto_approve_claim", "DomainAdapter", "auto_approve_claim", ["risk_scores"], ["auto_approval_records", "approval_status"], [], "low_risk_claim_auto_approver", {"risk_scores": "risk_scores"}, {"auto_approval_records": "auto_approval_records", "approval_status": "approval_status"}, {"approval_policy": "low_risk_standard"}),
                ("write_settlement_summary", "ReportGenerator", "write_settlement_summary", ["manual_adjudication_records", "auto_approval_records"], ["settlement_summary", "settlement_summary_status"], [], "claim_settlement_summary_writer", {"manual_adjudication_records": "manual_adjudication_records", "auto_approval_records": "auto_approval_records"}, {"settlement_summary": "settlement_summary", "summary_status": "settlement_summary_status"}, {"summary_name": "claim_settlement_summary"}),
            ],
            {"claims_database_resource": ("object", None, "claims_database"), "risk_scoring_service_resource": ("object", None, "risk_scoring_service")},
            [("ingest_claims", "score_claim_risk"), ("score_claim_risk", "route_claim"), ("route_claim", "manual_adjudication"), ("route_claim", "auto_approve_claim"), ("manual_adjudication", "write_settlement_summary"), ("auto_approve_claim", "write_settlement_summary")],
            [],
            {"branch_id": "claim_risk_route", "decision_intent": "route_claim", "decision_artifact": "claim_route_decision", "cases": [{"case_id": "high_risk", "condition": "claim_route_decision.route == manual_adjudication", "next_intents": ["manual_adjudication"]}, {"case_id": "low_risk", "condition": "claim_route_decision.route == auto_approve_claim", "next_intents": ["auto_approve_claim"]}], "merge_intent": "write_settlement_summary"},
            {"claims": 5, "high_risk": 1},
        ),
        (
            "val_marketing_attribution_fan_in",
            "Extract impressions, clicks, and purchases in parallel, join the channels, compute attribution metrics, publish a table, and send a campaign summary.",
            "fan_out_fan_in",
            base.systems([("ad_platform_api", "http_api", "Ad platform API"), ("commerce_database", "database", "Commerce database"), ("email_service", "http_api", "Email service")]),
            [
                ("extract_impressions", "Extractor", "extract_impressions", ["ad_platform_api_resource"], ["impressions", "impression_extract_status"], ["ad_platform_api"], "marketing_event_api_extractor", {"ad_platform_api": "ad_platform_api_resource"}, {"marketing_events": "impressions", "extraction_status": "impression_extract_status"}, {"event_type": "impressions", "lookback_days": 7}),
                ("extract_clicks", "Extractor", "extract_clicks", ["ad_platform_api_resource"], ["clicks", "click_extract_status"], ["ad_platform_api"], "marketing_event_api_extractor", {"ad_platform_api": "ad_platform_api_resource"}, {"marketing_events": "clicks", "extraction_status": "click_extract_status"}, {"event_type": "clicks", "lookback_days": 7}),
                ("extract_purchases", "Extractor", "extract_purchases", ["commerce_database_resource"], ["purchases", "purchase_extract_status"], ["commerce_database"], "commerce_purchase_event_extractor", {"commerce_database": "commerce_database_resource"}, {"purchase_events": "purchases", "extraction_status": "purchase_extract_status"}, {"purchase_query": "weekly_purchases"}),
                ("join_customer_events", "Integrator", "join_customer_events", ["impressions", "clicks", "purchases"], ["joined_customer_events", "join_status"], [], "customer_event_attribution_joiner", {"impressions": "impressions", "clicks": "clicks", "purchases": "purchases"}, {"joined_customer_events": "joined_customer_events", "join_status": "join_status"}, {"identity_key": "customer_id", "attribution_window_days": 7}),
                ("compute_attribution", "Aggregator", "compute_attribution", ["joined_customer_events"], ["attribution_metrics", "attribution_status"], [], "attribution_metric_calculator", {"joined_customer_events": "joined_customer_events"}, {"attribution_metrics": "attribution_metrics", "calculation_status": "attribution_status"}, {"model_name": "last_touch", "conversion_event": "purchase"}),
                ("publish_attribution_table", "Publisher", "publish_attribution_table", ["attribution_metrics", "commerce_database_resource"], ["attribution_table", "attribution_publication_status"], ["commerce_database"], "attribution_table_publisher", {"attribution_metrics": "attribution_metrics", "commerce_database": "commerce_database_resource"}, {"attribution_table": "attribution_table", "publication_status": "attribution_publication_status"}, {"target_table": "marketing_attribution", "write_mode": "replace"}),
                ("send_campaign_summary", "Notifier", "send_campaign_summary", ["attribution_table", "email_service_resource"], ["campaign_notification_status"], ["email_service"], "campaign_summary_notification_sender", {"attribution_table": "attribution_table", "email_service": "email_service_resource"}, {"campaign_notification_status": "campaign_notification_status"}, {"recipient_group": "campaign_ops", "subject": "Campaign attribution summary"}),
            ],
            {"ad_platform_api_resource": ("object", None, "ad_platform_api"), "commerce_database_resource": ("object", None, "commerce_database"), "email_service_resource": ("object", None, "email_service")},
            [("extract_impressions", "join_customer_events"), ("extract_clicks", "join_customer_events"), ("extract_purchases", "join_customer_events"), ("join_customer_events", "compute_attribution"), ("compute_attribution", "publish_attribution_table"), ("publish_attribution_table", "send_campaign_summary")],
            [{"group_id": "marketing_event_extraction", "intent_ids": ["extract_impressions", "extract_clicks", "extract_purchases"]}],
            None,
            {"campaign": "spring", "events": 100},
        ),
        (
            "val_data_quality_quarantine_gate",
            "Profile a customer extract, evaluate quality rules, load valid records, quarantine invalid records, and write an audit summary.",
            "branch_merge",
            base.systems([("customer_warehouse", "database", "Customer warehouse"), ("quarantine_bucket", "object_storage", "Quarantine bucket")]),
            [
                ("profile_customer_extract", "DataProfiler", "profile_customer_extract", ["customer_extract"], ["profile_report", "profile_status"], [], "customer_extract_profiler", {"customer_extract": "customer_extract"}, {"profile_report": "profile_report", "profile_status": "profile_status"}, {"profile_rules": {"null_threshold": 0.05}}),
                ("evaluate_quality_rules", "QualityCheck", "evaluate_quality_rules", ["profile_report", "customer_extract"], ["valid_records", "invalid_records", "quality_decision", "quality_status"], [], "customer_quality_rule_evaluator", {"profile_report": "profile_report", "customer_extract": "customer_extract"}, {"valid_records": "valid_records", "invalid_records": "invalid_records", "quality_decision": "quality_decision", "quality_status": "quality_status"}, {"quality_rules": {"required": ["customer_id", "email"]}}),
                ("load_valid_records", "Loader", "load_valid_records", ["valid_records", "customer_warehouse_resource"], ["valid_load_status"], ["customer_warehouse"], "valid_customer_records_loader", {"valid_records": "valid_records", "customer_warehouse": "customer_warehouse_resource"}, {"valid_load_status": "valid_load_status"}, {"target_table": "customer_validated", "write_mode": "upsert"}),
                ("quarantine_invalid_records", "Publisher", "quarantine_invalid_records", ["invalid_records", "quarantine_bucket_resource"], ["quarantine_reference", "quarantine_status"], ["quarantine_bucket"], "invalid_customer_records_quarantine_publisher", {"invalid_records": "invalid_records", "quarantine_bucket": "quarantine_bucket_resource"}, {"quarantine_reference": "quarantine_reference", "quarantine_status": "quarantine_status"}, {"quarantine_prefix": "customer_extract/"}),
                ("write_quality_audit", "ReportGenerator", "write_quality_audit", ["valid_load_status", "quarantine_status"], ["quality_audit", "audit_status"], [], "quality_audit_summary_writer", {"valid_load_status": "valid_load_status", "quarantine_status": "quarantine_status"}, {"quality_audit": "quality_audit", "audit_status": "audit_status"}, {"audit_name": "customer_quality_audit"}),
            ],
            {"customer_extract": ("table", None, None), "customer_warehouse_resource": ("object", None, "customer_warehouse"), "quarantine_bucket_resource": ("object", None, "quarantine_bucket")},
            [("profile_customer_extract", "evaluate_quality_rules"), ("evaluate_quality_rules", "load_valid_records"), ("evaluate_quality_rules", "quarantine_invalid_records"), ("load_valid_records", "write_quality_audit"), ("quarantine_invalid_records", "write_quality_audit")],
            [],
            {"branch_id": "quality_route", "decision_intent": "evaluate_quality_rules", "decision_artifact": "quality_decision", "cases": [{"case_id": "quality_pass", "condition": "quality_decision.route == load_valid_records", "next_intents": ["load_valid_records"]}, {"case_id": "quality_fail", "condition": "quality_decision.route == quarantine_invalid_records", "next_intents": ["quarantine_invalid_records"]}], "merge_intent": "write_quality_audit"},
            {"extract_rows": 200, "invalid_rows": 3},
        ),
        (
            "val_ml_feature_refresh",
            "Refresh raw events, transform features, validate drift statistics, publish a feature table, and notify the model team.",
            "staged_etl",
            base.systems([("event_lake", "object_storage", "Event lake"), ("feature_store", "database", "Feature store"), ("notification_service", "http_api", "Notification service")]),
            [
                ("extract_raw_events", "Extractor", "extract_raw_events", ["event_lake_resource"], ["raw_events", "event_extract_status"], ["event_lake"], "event_lake_raw_event_extractor", {"event_lake": "event_lake_resource"}, {"raw_events": "raw_events", "extraction_status": "event_extract_status"}, {"event_path": "events/", "lookback_hours": 24}),
                ("clean_event_records", "Transformer", "clean_event_records", ["raw_events"], ["clean_events", "cleaning_status"], [], "event_record_cleaner", {"raw_events": "raw_events"}, {"clean_events": "clean_events", "cleaning_status": "cleaning_status"}, {"cleaning_rules": {"drop_null_user_id": True}}),
                ("aggregate_user_features", "Aggregator", "aggregate_user_features", ["clean_events"], ["feature_table", "aggregation_status"], [], "user_feature_aggregator", {"clean_events": "clean_events"}, {"feature_table": "feature_table", "aggregation_status": "aggregation_status"}, {"feature_spec": {"windows": ["1d", "7d"]}}),
                ("compute_drift_statistics", "DataProfiler", "compute_drift_statistics", ["feature_table"], ["drift_report", "drift_status"], [], "feature_drift_statistics_computer", {"feature_table": "feature_table"}, {"drift_report": "drift_report", "drift_status": "drift_status"}, {"baseline_window": "30d", "drift_metrics": ["psi", "mean_shift"]}),
                ("validate_feature_table", "QualityCheck", "validate_feature_table", ["feature_table", "drift_report"], ["validated_feature_table", "feature_validation_status"], [], "feature_table_drift_validator", {"feature_table": "feature_table", "drift_report": "drift_report"}, {"validated_feature_table": "validated_feature_table", "validation_status": "feature_validation_status"}, {"drift_thresholds": {"psi": 0.2}}),
                ("publish_feature_table", "Publisher", "publish_feature_table", ["validated_feature_table", "feature_store_resource"], ["feature_publication_status"], ["feature_store"], "feature_store_table_publisher", {"validated_feature_table": "validated_feature_table", "feature_store": "feature_store_resource"}, {"feature_publication_status": "feature_publication_status"}, {"feature_table_name": "user_features_daily", "write_mode": "replace"}),
                ("notify_model_team", "Notifier", "notify_model_team", ["feature_publication_status", "notification_service_resource"], ["model_team_notification_status"], ["notification_service"], "model_team_notification_sender", {"feature_publication_status": "feature_publication_status", "notification_service": "notification_service_resource"}, {"model_team_notification_status": "model_team_notification_status"}, {"recipient_group": "model_team", "message_template": "feature_refresh_complete"}),
            ],
            {"event_lake_resource": ("object", None, "event_lake"), "feature_store_resource": ("object", None, "feature_store"), "notification_service_resource": ("object", None, "notification_service")},
            [("extract_raw_events", "clean_event_records"), ("clean_event_records", "aggregate_user_features"), ("aggregate_user_features", "compute_drift_statistics"), ("compute_drift_statistics", "validate_feature_table"), ("validate_feature_table", "publish_feature_table"), ("publish_feature_table", "notify_model_team")],
            [],
            None,
            {"events": 1000, "features": 25},
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
        )
        if pipeline == "val_data_quality_quarantine_gate":
            flow["control_flow"]["gates"] = [
                {
                    "gate_id": "quality_score_gate",
                    "sensor_intent": "evaluate_quality_rules",
                    "condition": "quality_score_available == true",
                    "gated_intents": ["load_valid_records", "quarantine_invalid_records", "write_quality_audit"],
                }
            ]
        task_outputs = {item["intent_id"]: item["outputs"] for item in flow["service_intents"]}
        reviews.append(write_instance(flow, task_outputs, fixture))

    review_dir = ROOT / "benchmark/catalog/review" / CATALOG_VERSION
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "candidate_relationships.private.json").write_text(
        json.dumps({"catalog_version": CATALOG_VERSION, "pipelines": reviews}, indent=2) + "\n",
        encoding="utf-8",
    )
    print("authored validation batch 03: 5 instances and catalogue 0.2.2")


if __name__ == "__main__":
    main()
