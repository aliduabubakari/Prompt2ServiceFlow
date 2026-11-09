#!/usr/bin/env python3
"""Author Validation-20 batch 04 as the final reviewed validation slice."""

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
CATALOG_VERSION = "0.2.3"
BASE_CATALOG_VERSION = "0.2.2"
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
    document["capability"]["keywords"] = list(dict.fromkeys(document["capability"]["keywords"]))
    document["invocation"]["image"] = "prompt2serviceflow/runtime:0.2.3"
    document["provenance"]["created_at"] = CREATED_AT
    document["provenance"]["source_refs"] = ["validation-batch-04:curated-extension"]
    document["provenance"]["notes"] = [
        "Curated from sparse Validation-20 batch 04 descriptions; bindings retain inference confidence."
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
        "multi_resource_readiness_sensor": descriptor(
            "multi_resource_readiness_sensor",
            "Sensor",
            "Checks that a configured set of upstream resources is ready for processing.",
            [port("resource_group", "object", channel="external_resource")],
            [port("readiness_decision", "json"), port("readiness_status", "status")],
            [parameter("readiness_condition"), parameter("minimum_ready_count", "integer")],
            network="required",
            secret="optional",
        ),
        "partner_feed_extractor": descriptor(
            "partner_feed_extractor",
            "Extractor",
            "Extracts one configured partner feed from a bound partner data source.",
            [port("partner_source", "object", channel="external_resource")],
            [port("partner_extract", "table"), port("extraction_status", "status")],
            [parameter("partner_name"), parameter("source_kind")],
            network="required",
            secret="optional",
        ),
        "partner_record_standardizer": descriptor(
            "partner_record_standardizer",
            "Transformer",
            "Standardizes multiple partner extracts into a common reconciliation schema.",
            [port("partner_a_extract", "table"), port("partner_b_extract", "table"), port("partner_c_extract", "table")],
            [port("standardized_records", "table"), port("standardization_status", "status")],
            [parameter("schema_profile", "object")],
        ),
        "federated_entity_matcher": descriptor(
            "federated_entity_matcher",
            "Reconciler",
            "Matches standardized partner records and identifies unresolved discrepancies.",
            [port("standardized_records", "table")],
            [port("clean_records", "table"), port("discrepancy_records", "table"), port("match_status", "status")],
            [parameter("match_keys", "array"), parameter("matching_policy")],
        ),
        "discrepancy_route_decider": descriptor(
            "discrepancy_route_decider",
            "DomainAdapter",
            "Routes reconciled partner records to clean publication or discrepancy review.",
            [port("clean_records", "table"), port("discrepancy_records", "table")],
            [port("route_decision", "json"), port("routing_status", "status")],
            [parameter("matched_route"), parameter("unresolved_route")],
        ),
        "clean_partner_record_publisher": descriptor(
            "clean_partner_record_publisher",
            "Publisher",
            "Publishes reconciled clean partner records to an approved output location.",
            [port("clean_records", "table")],
            [port("publication_status", "status")],
            [parameter("destination_name"), parameter("write_mode")],
        ),
        "review_case_opener": descriptor(
            "review_case_opener",
            "Publisher",
            "Opens review cases for unresolved business records in a case-management system.",
            [port("review_records", "table"), port("case_system", "object", channel="external_resource")],
            [port("review_cases", "json"), port("case_status", "status")],
            [parameter("case_type")],
            network="required",
            secret="optional",
        ),
        "audit_summary_writer": descriptor(
            "audit_summary_writer",
            "ReportGenerator",
            "Writes a bounded audit summary from two upstream processing statuses.",
            [port("primary_status", "status"), port("secondary_status", "status")],
            [port("audit_report", "json"), port("audit_status", "status")],
            [parameter("audit_name")],
        ),
        "hospital_operational_feed_extractor": descriptor(
            "hospital_operational_feed_extractor",
            "Extractor",
            "Extracts one hospital operational feed for capacity planning.",
            [port("hospital_source", "object", channel="external_resource")],
            [port("operational_feed", "table"), port("extraction_status", "status")],
            [parameter("feed_name")],
            network="required",
            secret="optional",
        ),
        "hospital_operational_state_merger": descriptor(
            "hospital_operational_state_merger",
            "Integrator",
            "Merges admissions, bed status, staffing, and discharge forecasts into operational state.",
            [port("admissions", "table"), port("bed_status", "table"), port("staffing_roster", "table"), port("discharge_forecast", "table")],
            [port("operational_state", "table"), port("merge_status", "status")],
            [parameter("merge_key")],
        ),
        "capacity_risk_calculator": descriptor(
            "capacity_risk_calculator",
            "ScoringService",
            "Computes hospital capacity risk from merged operational state.",
            [port("operational_state", "table")],
            [port("risk_report", "json"), port("risk_status", "status")],
            [parameter("risk_profile")],
        ),
        "alert_level_route_decider": descriptor(
            "alert_level_route_decider",
            "DomainAdapter",
            "Routes capacity risk to dashboard publication or escalation alerting.",
            [port("risk_report", "json")],
            [port("alert_route", "json"), port("routing_status", "status")],
            [parameter("critical_threshold", "number")],
        ),
        "capacity_dashboard_publisher": descriptor(
            "capacity_dashboard_publisher",
            "Publisher",
            "Publishes a hospital capacity dashboard payload.",
            [port("risk_report", "json")],
            [port("capacity_dashboard", "json"), port("dashboard_status", "status")],
            [parameter("dashboard_name")],
        ),
        "escalation_alert_sender": descriptor(
            "escalation_alert_sender",
            "Notifier",
            "Sends a critical escalation alert through a bound alerting service.",
            [port("risk_report", "json"), port("alerting_service", "object", channel="external_resource")],
            [port("alert_payload", "json"), port("alert_status", "status")],
            [parameter("recipient_group")],
            network="required",
            secret="optional",
        ),
        "financial_dataset_extractor": descriptor(
            "financial_dataset_extractor",
            "Extractor",
            "Extracts one configured financial risk input dataset from an external source.",
            [port("financial_source", "object", channel="external_resource")],
            [port("financial_dataset", "table"), port("extraction_status", "status")],
            [parameter("dataset_name")],
            network="required",
            secret="optional",
        ),
        "portfolio_stress_runner": descriptor(
            "portfolio_stress_runner",
            "ScoringService",
            "Runs one configured portfolio stress calculation using scenarios and positions.",
            [port("market_scenarios", "table"), port("portfolio_positions", "table"), port("risk_engine", "object", channel="external_resource")],
            [port("stress_result", "table"), port("stress_status", "status")],
            [parameter("stress_type")],
            network="required",
            secret="optional",
        ),
        "stress_result_aggregator": descriptor(
            "stress_result_aggregator",
            "Aggregator",
            "Aggregates credit, liquidity, and market stress results.",
            [port("credit_result", "table"), port("liquidity_result", "table"), port("market_result", "table")],
            [port("stress_results", "table"), port("aggregation_status", "status")],
            [parameter("aggregation_profile")],
        ),
        "capital_threshold_validator": descriptor(
            "capital_threshold_validator",
            "QualityCheck",
            "Validates aggregated stress results against capital thresholds.",
            [port("stress_results", "table")],
            [port("capital_validation", "json"), port("validation_status", "status")],
            [parameter("threshold_profile")],
        ),
        "risk_validation_route_decider": descriptor(
            "risk_validation_route_decider",
            "DomainAdapter",
            "Routes financial risk validation status to reporting or remediation.",
            [port("capital_validation", "json")],
            [port("validation_route", "json"), port("routing_status", "status")],
            [parameter("breach_route"), parameter("within_threshold_route")],
        ),
        "regulatory_report_writer": descriptor(
            "regulatory_report_writer",
            "ReportGenerator",
            "Writes a regulatory report from stress-test validation outputs.",
            [port("stress_results", "table"), port("capital_validation", "json")],
            [port("regulatory_report", "binary"), port("report_status", "status")],
            [parameter("report_name")],
        ),
        "model_input_archive_publisher": descriptor(
            "model_input_archive_publisher",
            "Publisher",
            "Archives stress-test model inputs in a regulated archive.",
            [port("market_scenarios", "table"), port("portfolio_positions", "table"), port("regulatory_archive", "object", channel="external_resource")],
            [port("archive_status", "status")],
            [parameter("archive_prefix")],
            network="required",
            secret="optional",
        ),
        "supply_chain_feed_extractor": descriptor(
            "supply_chain_feed_extractor",
            "Extractor",
            "Extracts one supply-chain operational feed from a configured source.",
            [port("supply_source", "object", channel="external_resource")],
            [port("supply_feed", "table"), port("extraction_status", "status")],
            [parameter("feed_name")],
            network="required",
            secret="optional",
        ),
        "supply_state_harmonizer": descriptor(
            "supply_state_harmonizer",
            "Integrator",
            "Harmonizes inventory, shipment, weather, and supplier-capacity feeds.",
            [port("inventory_snapshot", "table"), port("shipment_events", "table"), port("weather_alerts", "table"), port("supplier_capacity", "table")],
            [port("supply_state", "table"), port("harmonization_status", "status")],
            [parameter("state_profile", "object")],
        ),
        "disruption_risk_detector": descriptor(
            "disruption_risk_detector",
            "ScoringService",
            "Detects supply-chain disruption risk from harmonized supply state.",
            [port("supply_state", "table")],
            [port("disruption_risk", "json"), port("risk_status", "status")],
            [parameter("risk_profile")],
        ),
        "exception_severity_route_decider": descriptor(
            "exception_severity_route_decider",
            "DomainAdapter",
            "Routes supply-chain disruption risk by exception severity.",
            [port("disruption_risk", "json")],
            [port("severity_route", "json"), port("routing_status", "status")],
            [parameter("severe_threshold", "number")],
        ),
        "response_plan_generator": descriptor(
            "response_plan_generator",
            "DomainAdapter",
            "Generates a response plan for severe supply-chain exceptions.",
            [port("disruption_risk", "json")],
            [port("response_plan", "json"), port("plan_status", "status")],
            [parameter("planning_profile")],
        ),
        "operations_dashboard_publisher": descriptor(
            "operations_dashboard_publisher",
            "Publisher",
            "Publishes a global operations dashboard from disruption risk outputs.",
            [port("disruption_risk", "json")],
            [port("operations_dashboard", "json"), port("dashboard_status", "status")],
            [parameter("dashboard_name")],
        ),
        "regional_team_notifier": descriptor(
            "regional_team_notifier",
            "Notifier",
            "Notifies regional operations teams using a response plan.",
            [port("response_plan", "json"), port("notification_service", "object", channel="external_resource")],
            [port("notification_status", "notification")],
            [parameter("recipient_group")],
            network="required",
            secret="optional",
        ),
        "exception_snapshot_archiver": descriptor(
            "exception_snapshot_archiver",
            "Publisher",
            "Archives a supply-chain exception dashboard snapshot.",
            [port("operations_dashboard", "json")],
            [port("exception_archive", "object"), port("archive_status", "status")],
            [parameter("archive_name")],
        ),
        "fraud_source_loader": descriptor(
            "fraud_source_loader",
            "Extractor",
            "Loads one fraud-analysis source dataset from a stream or batch system.",
            [port("fraud_source", "object", channel="external_resource")],
            [port("fraud_dataset", "table"), port("load_status", "status")],
            [parameter("source_name")],
            network="required",
            secret="optional",
        ),
        "transaction_context_joiner": descriptor(
            "transaction_context_joiner",
            "Integrator",
            "Joins stream events, settlement records, and account history into transaction context.",
            [port("stream_events", "table"), port("settlement_records", "table"), port("account_history", "table")],
            [port("transaction_context", "table"), port("join_status", "status")],
            [parameter("join_key")],
        ),
        "transaction_fraud_risk_scorer": descriptor(
            "transaction_fraud_risk_scorer",
            "ScoringService",
            "Scores joined transaction context for account-level fraud risk.",
            [port("transaction_context", "table")],
            [port("risk_scores", "table"), port("scoring_status", "status")],
            [parameter("scoring_profile")],
        ),
        "fraud_risk_action_router": descriptor(
            "fraud_risk_action_router",
            "DomainAdapter",
            "Routes fraud risk scores to monitoring update or investigation case handling.",
            [port("risk_scores", "table")],
            [port("risk_action", "json"), port("routing_status", "status")],
            [parameter("risk_threshold", "number")],
        ),
        "fraud_monitoring_table_updater": descriptor(
            "fraud_monitoring_table_updater",
            "Loader",
            "Updates a monitoring table with low-risk fraud scoring outputs.",
            [port("risk_scores", "table"), port("monitoring_store", "object", channel="external_resource")],
            [port("monitoring_status", "status")],
            [parameter("target_table")],
            network="required",
            secret="optional",
        ),
        "risk_metric_publisher": descriptor(
            "risk_metric_publisher",
            "Publisher",
            "Publishes aggregate fraud risk metrics from monitoring updates.",
            [port("monitoring_status", "status")],
            [port("risk_metrics", "json"), port("metric_status", "status")],
            [parameter("metric_name")],
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
                "run_id": "curated-validation-batch-04",
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
        "http_json_request_extractor",
        "tabular_dataset_database_loader",
        "bi_dashboard_refresh_trigger",
        "parquet_tabular_data_profiler",
        "bulk_email_campaign_sender",
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
        public.append({"candidate_set_id": set_id, "source_step_refs": refs_by_service[service_id], "service_ids": options})
        private.append({"candidate_set_id": set_id, "required_service_id": service_id, "labels": {options[0]: "gold", options[1]: "semantic_mismatch", options[2]: "generic_escape_hatch"}})
        review_sets.append({"candidate_set_id": set_id, "required_service_id": service_id, "source_step_refs": refs_by_service[service_id], "candidates": [{"service_id": options[0], "label": "gold", "rationale": "Reviewed contract match."}, {"service_id": options[1], "label": "semantic_mismatch", "rationale": "Capability overlap without the required service contract."}, {"service_id": options[2], "label": "generic_escape_hatch", "rationale": "Generic alternative is less specific than the reviewed service."}]})
    return (
        {"candidate_set_version": "0.1.0", "benchmark_id": f"validation:{pipeline}", "catalog_snapshot": {"catalog_id": "serviceflow_catalog", "version": CATALOG_VERSION}, "candidate_sets": public},
        {"candidate_label_version": "0.1.0", "benchmark_id": f"validation:{pipeline}", "candidate_sets": private},
        {"pipeline_id": pipeline, "candidate_sets": review_sets, "new_distractor_services": [], "review_notes": ["Curated for Validation-20 batch 04; labels are private benchmark gold."]},
    )


def write_instance(flow: dict[str, Any], task_outputs: dict[str, list[str]], fixture: dict[str, Any]) -> dict[str, Any]:
    pipeline = flow["source"]["pipeline_id"]
    root = ROOT / "benchmark/instances/validation" / pipeline
    dump_yaml(root / "gold/serviceflow.yaml", flow)
    public, private, review = candidates(pipeline, flow["bindings"], flow["service_intents"])
    dump_yaml(root / "candidates/candidate_sets.yaml", public)
    dump_yaml(root / "gold/candidate_labels.yaml", private)
    dump_yaml(root / "gold/bindings.yaml", {"binding_gold_version": "0.1.0", "benchmark_id": flow["source"]["benchmark_id"], "bindings": [{key: item[key] for key in ["intent_id", "service_id", "service_version"]} for item in flow["bindings"]]})
    dump_yaml(root / "gold/artifact_mappings.yaml", {"artifact_mapping_version": "0.1.0", "benchmark_id": flow["source"]["benchmark_id"], "mappings": [{"intent_id": item["intent_id"], "inputs": {x["port"]: x["artifact_id"] for x in item["input_bindings"]}, "outputs": {x["port"]: x["artifact_id"] for x in item["output_bindings"]}} for item in flow["bindings"]]})

    tasks = []
    for number, item in enumerate(flow["service_intents"], start=1):
        task_id = item["intent_id"]
        filename = f"{number:02d}_{task_id}.py"
        (root / "runtime/scripts" / filename).write_text(base.mock_script(task_id, task_outputs[task_id]), encoding="utf-8")
        predecessors = [edge["from"] for edge in flow["control_flow"]["edges"] if edge["to"] == task_id]
        task = {"intent_id": task_id, "script": f"scripts/{filename}", "arguments": ["--workspace", "{workspace}", "--fixture", "{fixtures}/fixture.json"]}
        if predecessors:
            task["dependencies"] = predecessors
        tasks.append(task)
    dump_yaml(root / "runtime/manifest.yaml", {"runtime_manifest_version": "0.1.0", "pipeline_id": pipeline, "image": "python:3.12-slim", "workflow_parameters": [], "tasks": tasks, "scenarios": [{"name": "nominal", "parameters": {}}], "cron": {"schedule": "0 0 * * *", "timezone": "UTC"}})
    (root / "fixtures/inputs/fixture.json").write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    final_status = task_outputs[flow["service_intents"][-1]["intent_id"]][-1]
    dump_yaml(root / "gold/assertions.yaml", {"assertions_version": "0.1.0", "pipeline_id": pipeline, "scenarios": [{"scenario": "nominal", "assertions": [{"assertion_id": "final_status_succeeds", "type": "json_path_equals", "path": f"artifacts/{final_status}.json", "json_path": "success", "expected": True}]}]})
    (root / "README.md").write_text(f"# {pipeline}\n\nValidation-20 batch 04. Source evidence is low-information; service bindings are explicitly marked strongly inferred. The runtime uses deterministic, task-specific mock scripts and does not claim external-system execution.\n", encoding="utf-8")
    write_resources(root)
    return review


def build_flow(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return helpers.build_flow(*args, **kwargs)


def main() -> None:
    prepare_catalogue()
    reviews = []
    # To keep this final batch maintainable, each row follows the shared tuple
    # shape from prior validation batches:
    # intent, category, source step, inputs, outputs, systems, service, input map,
    # output map, parameter map.
    definitions = []

    definitions.append((
        "val_federated_partner_reconciliation",
        "Wait for partner extracts, ingest three feeds in parallel, reconcile discrepancies, route unresolved records to review, and publish consolidated outputs.",
        "mixed",
        base.systems([("partner_resources", "other", "Federated partner extract resources"), ("review_case_system", "http_api", "Review case system")]),
        [
            ("wait_for_partner_extracts", "Sensor", "wait_for_partner_extracts", ["partner_resources"], ["partner_ready", "partner_ready_status"], ["partner_resources"], "multi_resource_readiness_sensor", {"resource_group": "partner_resources"}, {"readiness_decision": "partner_ready", "readiness_status": "partner_ready_status"}, {"readiness_condition": "all_partner_files_arrived", "minimum_ready_count": 3}),
            ("ingest_partner_a", "Extractor", "ingest_partner_a", ["partner_resources"], ["partner_a_extract", "partner_a_status"], ["partner_resources"], "partner_feed_extractor", {"partner_source": "partner_resources"}, {"partner_extract": "partner_a_extract", "extraction_status": "partner_a_status"}, {"partner_name": "partner_a", "source_kind": "sftp"}),
            ("ingest_partner_b", "Extractor", "ingest_partner_b", ["partner_resources"], ["partner_b_extract", "partner_b_status"], ["partner_resources"], "partner_feed_extractor", {"partner_source": "partner_resources"}, {"partner_extract": "partner_b_extract", "extraction_status": "partner_b_status"}, {"partner_name": "partner_b", "source_kind": "api"}),
            ("ingest_partner_c", "Extractor", "ingest_partner_c", ["partner_resources"], ["partner_c_extract", "partner_c_status"], ["partner_resources"], "partner_feed_extractor", {"partner_source": "partner_resources"}, {"partner_extract": "partner_c_extract", "extraction_status": "partner_c_status"}, {"partner_name": "partner_c", "source_kind": "bucket"}),
            ("standardize_records", "Transformer", "standardize_records", ["partner_a_extract", "partner_b_extract", "partner_c_extract"], ["standardized_records", "standardization_status"], [], "partner_record_standardizer", {"partner_a_extract": "partner_a_extract", "partner_b_extract": "partner_b_extract", "partner_c_extract": "partner_c_extract"}, {"standardized_records": "standardized_records", "standardization_status": "standardization_status"}, {"schema_profile": {"entity": "partner"}}),
            ("match_entities", "Reconciler", "match_entities", ["standardized_records"], ["clean_records", "discrepancy_records", "match_status"], [], "federated_entity_matcher", {"standardized_records": "standardized_records"}, {"clean_records": "clean_records", "discrepancy_records": "discrepancy_records", "match_status": "match_status"}, {"match_keys": ["partner_id"], "matching_policy": "deterministic"}),
            ("route_discrepancies", "DomainAdapter", "route_discrepancies", ["clean_records", "discrepancy_records"], ["discrepancy_route", "discrepancy_routing_status"], [], "discrepancy_route_decider", {"clean_records": "clean_records", "discrepancy_records": "discrepancy_records"}, {"route_decision": "discrepancy_route", "routing_status": "discrepancy_routing_status"}, {"matched_route": "publish_clean_records", "unresolved_route": "open_review_cases"}),
            ("publish_clean_records", "Publisher", "publish_clean_records", ["clean_records"], ["clean_publication_status"], [], "clean_partner_record_publisher", {"clean_records": "clean_records"}, {"publication_status": "clean_publication_status"}, {"destination_name": "consolidated_partner_records", "write_mode": "replace"}),
            ("open_review_cases", "Publisher", "open_review_cases", ["discrepancy_records", "review_case_system"], ["review_cases", "review_case_status"], ["review_case_system"], "review_case_opener", {"review_records": "discrepancy_records", "case_system": "review_case_system"}, {"review_cases": "review_cases", "case_status": "review_case_status"}, {"case_type": "partner_discrepancy"}),
            ("write_reconciliation_audit", "ReportGenerator", "write_reconciliation_audit", ["clean_publication_status", "review_case_status"], ["audit_report", "audit_status"], [], "audit_summary_writer", {"primary_status": "clean_publication_status", "secondary_status": "review_case_status"}, {"audit_report": "audit_report", "audit_status": "audit_status"}, {"audit_name": "partner_reconciliation"}),
        ],
        {"partner_resources": ("object", None, "partner_resources"), "review_case_system": ("object", None, "review_case_system")},
        [("wait_for_partner_extracts", "ingest_partner_a"), ("wait_for_partner_extracts", "ingest_partner_b"), ("wait_for_partner_extracts", "ingest_partner_c"), ("ingest_partner_a", "standardize_records"), ("ingest_partner_b", "standardize_records"), ("ingest_partner_c", "standardize_records"), ("standardize_records", "match_entities"), ("match_entities", "route_discrepancies"), ("route_discrepancies", "publish_clean_records"), ("route_discrepancies", "open_review_cases"), ("publish_clean_records", "write_reconciliation_audit"), ("open_review_cases", "write_reconciliation_audit")],
        [{"group_id": "partner_ingestion", "intent_ids": ["ingest_partner_a", "ingest_partner_b", "ingest_partner_c"]}],
        {"branch_id": "discrepancy_route", "decision_intent": "route_discrepancies", "decision_artifact": "discrepancy_route", "cases": [{"case_id": "matched", "condition": "discrepancy_route.route == publish_clean_records", "next_intents": ["publish_clean_records"]}, {"case_id": "unresolved", "condition": "discrepancy_route.route == open_review_cases", "next_intents": ["open_review_cases"]}], "merge_intent": "write_reconciliation_audit"},
        {"gate_id": "partner_extract_gate", "sensor_intent": "wait_for_partner_extracts", "condition": "all_partner_files_arrived == true", "gated_intents": ["ingest_partner_a", "ingest_partner_b", "ingest_partner_c", "standardize_records", "match_entities"]},
        {"partners": 3},
    ))

    definitions.append((
        "val_hospital_capacity_command_center",
        "Wait for clinical census data, combine operational feeds, compute capacity risk, and route capacity alerts.",
        "mixed",
        base.systems([("hospital_sources", "database", "Hospital operational sources"), ("alerting_service", "http_api", "Alerting service")]),
        [
            ("wait_for_census_snapshot", "Sensor", "wait_for_census_snapshot", ["hospital_sources"], ["census_ready", "census_ready_status"], ["hospital_sources"], "multi_resource_readiness_sensor", {"resource_group": "hospital_sources"}, {"readiness_decision": "census_ready", "readiness_status": "census_ready_status"}, {"readiness_condition": "census_snapshot_ready", "minimum_ready_count": 1}),
            ("extract_admissions", "Extractor", "extract_admissions", ["hospital_sources"], ["admissions", "admissions_status"], ["hospital_sources"], "hospital_operational_feed_extractor", {"hospital_source": "hospital_sources"}, {"operational_feed": "admissions", "extraction_status": "admissions_status"}, {"feed_name": "admissions"}),
            ("extract_bed_status", "Extractor", "extract_bed_status", ["hospital_sources"], ["bed_status", "bed_status_extract_status"], ["hospital_sources"], "hospital_operational_feed_extractor", {"hospital_source": "hospital_sources"}, {"operational_feed": "bed_status", "extraction_status": "bed_status_extract_status"}, {"feed_name": "bed_status"}),
            ("extract_staffing_roster", "Extractor", "extract_staffing_roster", ["hospital_sources"], ["staffing_roster", "staffing_status"], ["hospital_sources"], "hospital_operational_feed_extractor", {"hospital_source": "hospital_sources"}, {"operational_feed": "staffing_roster", "extraction_status": "staffing_status"}, {"feed_name": "staffing_roster"}),
            ("extract_discharge_forecast", "Extractor", "extract_discharge_forecast", ["hospital_sources"], ["discharge_forecast", "forecast_status"], ["hospital_sources"], "hospital_operational_feed_extractor", {"hospital_source": "hospital_sources"}, {"operational_feed": "discharge_forecast", "extraction_status": "forecast_status"}, {"feed_name": "discharge_forecast"}),
            ("merge_operational_state", "Integrator", "merge_operational_state", ["admissions", "bed_status", "staffing_roster", "discharge_forecast"], ["operational_state", "operational_merge_status"], [], "hospital_operational_state_merger", {"admissions": "admissions", "bed_status": "bed_status", "staffing_roster": "staffing_roster", "discharge_forecast": "discharge_forecast"}, {"operational_state": "operational_state", "merge_status": "operational_merge_status"}, {"merge_key": "hospital_unit"}),
            ("compute_capacity_risk", "ScoringService", "compute_capacity_risk", ["operational_state"], ["risk_report", "capacity_risk_status"], [], "capacity_risk_calculator", {"operational_state": "operational_state"}, {"risk_report": "risk_report", "risk_status": "capacity_risk_status"}, {"risk_profile": "capacity_standard"}),
            ("route_alert_level", "DomainAdapter", "route_alert_level", ["risk_report"], ["alert_route", "alert_route_status"], [], "alert_level_route_decider", {"risk_report": "risk_report"}, {"alert_route": "alert_route", "routing_status": "alert_route_status"}, {"critical_threshold": 0.8}),
            ("publish_dashboard", "Publisher", "publish_dashboard", ["risk_report"], ["capacity_dashboard", "dashboard_status"], [], "capacity_dashboard_publisher", {"risk_report": "risk_report"}, {"capacity_dashboard": "capacity_dashboard", "dashboard_status": "dashboard_status"}, {"dashboard_name": "capacity_command_center"}),
            ("send_escalation_alert", "Notifier", "send_escalation_alert", ["risk_report", "alerting_service"], ["alert_payload", "alert_status"], ["alerting_service"], "escalation_alert_sender", {"risk_report": "risk_report", "alerting_service": "alerting_service"}, {"alert_payload": "alert_payload", "alert_status": "alert_status"}, {"recipient_group": "capacity_escalation"}),
        ],
        {"hospital_sources": ("object", None, "hospital_sources"), "alerting_service": ("object", None, "alerting_service")},
        [("wait_for_census_snapshot", "extract_admissions"), ("wait_for_census_snapshot", "extract_bed_status"), ("wait_for_census_snapshot", "extract_staffing_roster"), ("wait_for_census_snapshot", "extract_discharge_forecast"), ("extract_admissions", "merge_operational_state"), ("extract_bed_status", "merge_operational_state"), ("extract_staffing_roster", "merge_operational_state"), ("extract_discharge_forecast", "merge_operational_state"), ("merge_operational_state", "compute_capacity_risk"), ("compute_capacity_risk", "route_alert_level"), ("route_alert_level", "publish_dashboard"), ("route_alert_level", "send_escalation_alert")],
        [{"group_id": "hospital_feed_extraction", "intent_ids": ["extract_admissions", "extract_bed_status", "extract_staffing_roster", "extract_discharge_forecast"]}],
        {"branch_id": "capacity_alert_route", "decision_intent": "route_alert_level", "decision_artifact": "alert_route", "cases": [{"case_id": "normal", "condition": "alert_route.level == normal", "next_intents": ["publish_dashboard"]}, {"case_id": "critical", "condition": "alert_route.level == critical", "next_intents": ["send_escalation_alert"]}]},
        {"gate_id": "census_snapshot_gate", "sensor_intent": "wait_for_census_snapshot", "condition": "census_snapshot_ready == true", "gated_intents": ["extract_admissions", "extract_bed_status", "extract_staffing_roster", "extract_discharge_forecast"]},
        {"units": 8},
    ))

    definitions.append((
        "val_financial_risk_stress_testing",
        "Load market scenarios and portfolio positions, run stress calculations, validate thresholds, route validation status, report, remediate, and archive.",
        "mixed",
        base.systems([("market_data_api", "http_api", "Market data API"), ("portfolio_warehouse", "database", "Portfolio warehouse"), ("risk_engine", "http_api", "Risk engine"), ("regulatory_archive", "object_storage", "Regulatory archive"), ("review_case_system", "http_api", "Risk remediation case system")]),
        [
            ("load_market_scenarios", "Extractor", "load_market_scenarios", ["market_data_api"], ["market_scenarios", "scenario_load_status"], ["market_data_api"], "financial_dataset_extractor", {"financial_source": "market_data_api"}, {"financial_dataset": "market_scenarios", "extraction_status": "scenario_load_status"}, {"dataset_name": "market_scenarios"}),
            ("load_portfolio_positions", "Extractor", "load_portfolio_positions", ["portfolio_warehouse"], ["portfolio_positions", "position_load_status"], ["portfolio_warehouse"], "financial_dataset_extractor", {"financial_source": "portfolio_warehouse"}, {"financial_dataset": "portfolio_positions", "extraction_status": "position_load_status"}, {"dataset_name": "portfolio_positions"}),
            ("run_credit_stress", "ScoringService", "run_credit_stress", ["market_scenarios", "portfolio_positions", "risk_engine"], ["credit_stress_result", "credit_stress_status"], ["risk_engine"], "portfolio_stress_runner", {"market_scenarios": "market_scenarios", "portfolio_positions": "portfolio_positions", "risk_engine": "risk_engine"}, {"stress_result": "credit_stress_result", "stress_status": "credit_stress_status"}, {"stress_type": "credit"}),
            ("run_liquidity_stress", "ScoringService", "run_liquidity_stress", ["market_scenarios", "portfolio_positions", "risk_engine"], ["liquidity_stress_result", "liquidity_stress_status"], ["risk_engine"], "portfolio_stress_runner", {"market_scenarios": "market_scenarios", "portfolio_positions": "portfolio_positions", "risk_engine": "risk_engine"}, {"stress_result": "liquidity_stress_result", "stress_status": "liquidity_stress_status"}, {"stress_type": "liquidity"}),
            ("run_market_stress", "ScoringService", "run_market_stress", ["market_scenarios", "portfolio_positions", "risk_engine"], ["market_stress_result", "market_stress_status"], ["risk_engine"], "portfolio_stress_runner", {"market_scenarios": "market_scenarios", "portfolio_positions": "portfolio_positions", "risk_engine": "risk_engine"}, {"stress_result": "market_stress_result", "stress_status": "market_stress_status"}, {"stress_type": "market"}),
            ("aggregate_stress_results", "Aggregator", "aggregate_stress_results", ["credit_stress_result", "liquidity_stress_result", "market_stress_result"], ["stress_results", "stress_aggregation_status"], [], "stress_result_aggregator", {"credit_result": "credit_stress_result", "liquidity_result": "liquidity_stress_result", "market_result": "market_stress_result"}, {"stress_results": "stress_results", "aggregation_status": "stress_aggregation_status"}, {"aggregation_profile": "regulatory"}),
            ("validate_capital_thresholds", "QualityCheck", "validate_capital_thresholds", ["stress_results"], ["capital_validation", "capital_validation_status"], [], "capital_threshold_validator", {"stress_results": "stress_results"}, {"capital_validation": "capital_validation", "validation_status": "capital_validation_status"}, {"threshold_profile": "basel"}),
            ("route_validation_status", "DomainAdapter", "route_validation_status", ["capital_validation"], ["validation_route", "validation_route_status"], [], "risk_validation_route_decider", {"capital_validation": "capital_validation"}, {"validation_route": "validation_route", "routing_status": "validation_route_status"}, {"breach_route": "open_remediation_ticket", "within_threshold_route": "write_regulatory_report"}),
            ("write_regulatory_report", "ReportGenerator", "write_regulatory_report", ["stress_results", "capital_validation"], ["regulatory_report", "report_status"], [], "regulatory_report_writer", {"stress_results": "stress_results", "capital_validation": "capital_validation"}, {"regulatory_report": "regulatory_report", "report_status": "report_status"}, {"report_name": "stress_test"}),
            ("open_remediation_ticket", "Publisher", "open_remediation_ticket", ["stress_results", "review_case_system"], ["remediation_ticket", "remediation_status"], ["review_case_system"], "review_case_opener", {"review_records": "stress_results", "case_system": "review_case_system"}, {"review_cases": "remediation_ticket", "case_status": "remediation_status"}, {"case_type": "capital_breach"}),
            ("archive_model_inputs", "Publisher", "archive_model_inputs", ["market_scenarios", "portfolio_positions", "regulatory_archive"], ["archive_status"], ["regulatory_archive"], "model_input_archive_publisher", {"market_scenarios": "market_scenarios", "portfolio_positions": "portfolio_positions", "regulatory_archive": "regulatory_archive"}, {"archive_status": "archive_status"}, {"archive_prefix": "stress-inputs/"}),
        ],
        {"market_data_api": ("object", None, "market_data_api"), "portfolio_warehouse": ("object", None, "portfolio_warehouse"), "risk_engine": ("object", None, "risk_engine"), "regulatory_archive": ("object", None, "regulatory_archive"), "review_case_system": ("object", None, "regulatory_archive")},
        [("load_market_scenarios", "run_credit_stress"), ("load_market_scenarios", "run_liquidity_stress"), ("load_market_scenarios", "run_market_stress"), ("load_portfolio_positions", "run_credit_stress"), ("load_portfolio_positions", "run_liquidity_stress"), ("load_portfolio_positions", "run_market_stress"), ("run_credit_stress", "aggregate_stress_results"), ("run_liquidity_stress", "aggregate_stress_results"), ("run_market_stress", "aggregate_stress_results"), ("aggregate_stress_results", "validate_capital_thresholds"), ("validate_capital_thresholds", "route_validation_status"), ("route_validation_status", "write_regulatory_report"), ("route_validation_status", "open_remediation_ticket"), ("write_regulatory_report", "archive_model_inputs")],
        [{"group_id": "stress_calculations", "intent_ids": ["run_credit_stress", "run_liquidity_stress", "run_market_stress"]}],
        {"branch_id": "risk_validation_route", "decision_intent": "route_validation_status", "decision_artifact": "validation_route", "cases": [{"case_id": "within_threshold", "condition": "validation_route.route == write_regulatory_report", "next_intents": ["write_regulatory_report"]}, {"case_id": "breach_detected", "condition": "validation_route.route == open_remediation_ticket", "next_intents": ["open_remediation_ticket"]}]},
        {"gate_id": "stress_results_gate", "sensor_intent": "validate_capital_thresholds", "condition": "all_stress_results_available == true", "gated_intents": ["route_validation_status", "write_regulatory_report", "open_remediation_ticket"]},
        {"scenarios": 3},
    ))

    # Final two definitions use the same compact pattern.
    definitions.extend(build_supply_and_fraud_definitions())

    for pipeline, purpose, topology, systems, rows, seed_artifacts, edges, parallel, branch, gate, fixture in definitions:
        flow = build_flow(pipeline, purpose, topology, systems, rows, seed_artifacts, edges, parallel_groups=parallel if isinstance(parallel, list) else None, branches=[branch] if branch else None, gates=[gate] if gate else None)
        task_outputs = {item["intent_id"]: item["outputs"] for item in flow["service_intents"]}
        reviews.append(write_instance(flow, task_outputs, fixture))

    review_dir = ROOT / "benchmark/catalog/review" / CATALOG_VERSION
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "candidate_relationships.private.json").write_text(json.dumps({"catalog_version": CATALOG_VERSION, "pipelines": reviews}, indent=2) + "\n", encoding="utf-8")
    print("authored validation batch 04: 5 instances and catalogue 0.2.3")


def build_supply_and_fraud_definitions() -> list[tuple[Any, ...]]:
    supply = (
        "val_supply_chain_exception_management",
        "Ingest supply-chain feeds, detect disruption risk, branch severe exceptions to response planning, and publish operations outputs.",
        "mixed",
        base.systems([("supply_sources", "other", "Supply-chain sources"), ("notification_service", "http_api", "Notification service")]),
        [
            ("wait_for_supplier_feeds", "Sensor", "wait_for_supplier_feeds", ["supply_sources"], ["supplier_feeds_ready", "supplier_feed_status"], ["supply_sources"], "multi_resource_readiness_sensor", {"resource_group": "supply_sources"}, {"readiness_decision": "supplier_feeds_ready", "readiness_status": "supplier_feed_status"}, {"readiness_condition": "minimum_feed_count_met", "minimum_ready_count": 3}),
            ("ingest_inventory", "Extractor", "ingest_inventory", ["supply_sources"], ["inventory_snapshot", "inventory_status"], ["supply_sources"], "supply_chain_feed_extractor", {"supply_source": "supply_sources"}, {"supply_feed": "inventory_snapshot", "extraction_status": "inventory_status"}, {"feed_name": "inventory"}),
            ("ingest_shipments", "Extractor", "ingest_shipments", ["supply_sources"], ["shipment_events", "shipment_status"], ["supply_sources"], "supply_chain_feed_extractor", {"supply_source": "supply_sources"}, {"supply_feed": "shipment_events", "extraction_status": "shipment_status"}, {"feed_name": "shipments"}),
            ("ingest_weather_alerts", "Extractor", "ingest_weather_alerts", ["supply_sources"], ["weather_alerts", "weather_status"], ["supply_sources"], "supply_chain_feed_extractor", {"supply_source": "supply_sources"}, {"supply_feed": "weather_alerts", "extraction_status": "weather_status"}, {"feed_name": "weather_alerts"}),
            ("ingest_supplier_capacity", "Extractor", "ingest_supplier_capacity", ["supply_sources"], ["supplier_capacity", "capacity_status"], ["supply_sources"], "supply_chain_feed_extractor", {"supply_source": "supply_sources"}, {"supply_feed": "supplier_capacity", "extraction_status": "capacity_status"}, {"feed_name": "supplier_capacity"}),
            ("harmonize_supply_state", "Integrator", "harmonize_supply_state", ["inventory_snapshot", "shipment_events", "weather_alerts", "supplier_capacity"], ["supply_state", "supply_harmonization_status"], [], "supply_state_harmonizer", {"inventory_snapshot": "inventory_snapshot", "shipment_events": "shipment_events", "weather_alerts": "weather_alerts", "supplier_capacity": "supplier_capacity"}, {"supply_state": "supply_state", "harmonization_status": "supply_harmonization_status"}, {"state_profile": {"grain": "sku_region"}}),
            ("detect_disruption_risk", "ScoringService", "detect_disruption_risk", ["supply_state"], ["disruption_risk", "disruption_risk_status"], [], "disruption_risk_detector", {"supply_state": "supply_state"}, {"disruption_risk": "disruption_risk", "risk_status": "disruption_risk_status"}, {"risk_profile": "global_supply"}),
            ("route_exception_severity", "DomainAdapter", "route_exception_severity", ["disruption_risk"], ["severity_route", "severity_route_status"], [], "exception_severity_route_decider", {"disruption_risk": "disruption_risk"}, {"severity_route": "severity_route", "routing_status": "severity_route_status"}, {"severe_threshold": 0.8}),
            ("generate_response_plan", "DomainAdapter", "generate_response_plan", ["disruption_risk"], ["response_plan", "response_plan_status"], [], "response_plan_generator", {"disruption_risk": "disruption_risk"}, {"response_plan": "response_plan", "plan_status": "response_plan_status"}, {"planning_profile": "regional"}),
            ("publish_operations_dashboard", "Publisher", "publish_operations_dashboard", ["disruption_risk"], ["operations_dashboard", "dashboard_status"], [], "operations_dashboard_publisher", {"disruption_risk": "disruption_risk"}, {"operations_dashboard": "operations_dashboard", "dashboard_status": "dashboard_status"}, {"dashboard_name": "global_supply"}),
            ("notify_regional_teams", "Notifier", "notify_regional_teams", ["response_plan", "notification_service"], ["notification_status"], ["notification_service"], "regional_team_notifier", {"response_plan": "response_plan", "notification_service": "notification_service"}, {"notification_status": "notification_status"}, {"recipient_group": "regional_ops"}),
            ("archive_exception_snapshot", "Publisher", "archive_exception_snapshot", ["operations_dashboard"], ["exception_archive", "archive_status"], [], "exception_snapshot_archiver", {"operations_dashboard": "operations_dashboard"}, {"exception_archive": "exception_archive", "archive_status": "archive_status"}, {"archive_name": "exception_snapshot"}),
        ],
        {"supply_sources": ("object", None, "supply_sources"), "notification_service": ("object", None, "notification_service")},
        [("wait_for_supplier_feeds", "ingest_inventory"), ("wait_for_supplier_feeds", "ingest_shipments"), ("wait_for_supplier_feeds", "ingest_weather_alerts"), ("wait_for_supplier_feeds", "ingest_supplier_capacity"), ("ingest_inventory", "harmonize_supply_state"), ("ingest_shipments", "harmonize_supply_state"), ("ingest_weather_alerts", "harmonize_supply_state"), ("ingest_supplier_capacity", "harmonize_supply_state"), ("harmonize_supply_state", "detect_disruption_risk"), ("detect_disruption_risk", "route_exception_severity"), ("route_exception_severity", "generate_response_plan"), ("route_exception_severity", "publish_operations_dashboard"), ("generate_response_plan", "notify_regional_teams"), ("publish_operations_dashboard", "archive_exception_snapshot")],
        [{"group_id": "supply_feed_ingestion", "intent_ids": ["ingest_inventory", "ingest_shipments", "ingest_weather_alerts", "ingest_supplier_capacity"]}],
        {"branch_id": "exception_severity_route", "decision_intent": "route_exception_severity", "decision_artifact": "severity_route", "cases": [{"case_id": "normal", "condition": "severity_route.route == publish_operations_dashboard", "next_intents": ["publish_operations_dashboard"]}, {"case_id": "severe", "condition": "severity_route.route == generate_response_plan", "next_intents": ["generate_response_plan"]}]},
        {"gate_id": "supplier_feed_gate", "sensor_intent": "wait_for_supplier_feeds", "condition": "minimum_feed_count_met == true", "gated_intents": ["ingest_inventory", "ingest_shipments", "ingest_weather_alerts", "ingest_supplier_capacity"]},
        {"feeds": 4},
    )
    fraud = (
        "val_stream_batch_fraud_bridge",
        "Wait for stream checkpoints, combine online events with batch history, route suspicious accounts, and update monitoring outputs.",
        "mixed",
        base.systems([("fraud_sources", "other", "Fraud stream and batch sources"), ("monitoring_store", "database", "Fraud monitoring store"), ("case_management_system", "http_api", "Case management system")]),
        [
            ("wait_for_stream_checkpoint", "Sensor", "wait_for_stream_checkpoint", ["fraud_sources"], ["checkpoint_ready", "checkpoint_status"], ["fraud_sources"], "multi_resource_readiness_sensor", {"resource_group": "fraud_sources"}, {"readiness_decision": "checkpoint_ready", "readiness_status": "checkpoint_status"}, {"readiness_condition": "checkpoint_committed", "minimum_ready_count": 1}),
            ("load_stream_events", "Extractor", "load_stream_events", ["fraud_sources"], ["stream_events", "stream_load_status"], ["fraud_sources"], "fraud_source_loader", {"fraud_source": "fraud_sources"}, {"fraud_dataset": "stream_events", "load_status": "stream_load_status"}, {"source_name": "stream_events"}),
            ("load_batch_settlements", "Extractor", "load_batch_settlements", ["fraud_sources"], ["settlement_records", "settlement_load_status"], ["fraud_sources"], "fraud_source_loader", {"fraud_source": "fraud_sources"}, {"fraud_dataset": "settlement_records", "load_status": "settlement_load_status"}, {"source_name": "settlements"}),
            ("load_account_history", "Extractor", "load_account_history", ["fraud_sources"], ["account_history", "account_history_status"], ["fraud_sources"], "fraud_source_loader", {"fraud_source": "fraud_sources"}, {"fraud_dataset": "account_history", "load_status": "account_history_status"}, {"source_name": "account_history"}),
            ("join_transaction_context", "Integrator", "join_transaction_context", ["stream_events", "settlement_records", "account_history"], ["transaction_context", "context_join_status"], [], "transaction_context_joiner", {"stream_events": "stream_events", "settlement_records": "settlement_records", "account_history": "account_history"}, {"transaction_context": "transaction_context", "join_status": "context_join_status"}, {"join_key": "account_id"}),
            ("score_fraud_risk", "ScoringService", "score_fraud_risk", ["transaction_context"], ["risk_scores", "risk_scoring_status"], [], "transaction_fraud_risk_scorer", {"transaction_context": "transaction_context"}, {"risk_scores": "risk_scores", "scoring_status": "risk_scoring_status"}, {"scoring_profile": "hybrid"}),
            ("route_risk_action", "DomainAdapter", "route_risk_action", ["risk_scores"], ["risk_action", "risk_route_status"], [], "fraud_risk_action_router", {"risk_scores": "risk_scores"}, {"risk_action": "risk_action", "routing_status": "risk_route_status"}, {"risk_threshold": 0.75}),
            ("update_monitoring_table", "Loader", "update_monitoring_table", ["risk_scores", "monitoring_store"], ["monitoring_status"], ["monitoring_store"], "fraud_monitoring_table_updater", {"risk_scores": "risk_scores", "monitoring_store": "monitoring_store"}, {"monitoring_status": "monitoring_status"}, {"target_table": "fraud_monitoring"}),
            ("open_investigation_case", "Publisher", "open_investigation_case", ["risk_scores", "case_management_system"], ["investigation_cases", "investigation_case_status"], ["case_management_system"], "review_case_opener", {"review_records": "risk_scores", "case_system": "case_management_system"}, {"review_cases": "investigation_cases", "case_status": "investigation_case_status"}, {"case_type": "fraud_investigation"}),
            ("publish_risk_metrics", "Publisher", "publish_risk_metrics", ["monitoring_status"], ["risk_metrics", "metric_status"], [], "risk_metric_publisher", {"monitoring_status": "monitoring_status"}, {"risk_metrics": "risk_metrics", "metric_status": "metric_status"}, {"metric_name": "fraud_risk"}),
        ],
        {"fraud_sources": ("object", None, "fraud_sources"), "monitoring_store": ("object", None, "monitoring_store"), "case_management_system": ("object", None, "case_management_system")},
        [("wait_for_stream_checkpoint", "load_stream_events"), ("wait_for_stream_checkpoint", "load_batch_settlements"), ("load_stream_events", "join_transaction_context"), ("load_batch_settlements", "join_transaction_context"), ("load_account_history", "join_transaction_context"), ("join_transaction_context", "score_fraud_risk"), ("score_fraud_risk", "route_risk_action"), ("route_risk_action", "update_monitoring_table"), ("route_risk_action", "open_investigation_case"), ("update_monitoring_table", "publish_risk_metrics")],
        [{"group_id": "fraud_source_loads", "intent_ids": ["load_stream_events", "load_batch_settlements", "load_account_history"]}],
        {"branch_id": "fraud_risk_route", "decision_intent": "route_risk_action", "decision_artifact": "risk_action", "cases": [{"case_id": "low_risk", "condition": "risk_action.route == update_monitoring_table", "next_intents": ["update_monitoring_table"]}, {"case_id": "high_risk", "condition": "risk_action.route == open_investigation_case", "next_intents": ["open_investigation_case"]}]},
        {"gate_id": "stream_checkpoint_gate", "sensor_intent": "wait_for_stream_checkpoint", "condition": "checkpoint_committed == true", "gated_intents": ["load_stream_events", "load_batch_settlements"]},
        {"transactions": 1000},
    )
    return [supply, fraud]


if __name__ == "__main__":
    main()
