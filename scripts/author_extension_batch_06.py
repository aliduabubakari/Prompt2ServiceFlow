#!/usr/bin/env python3
"""Author Extension-50 batch 06 event/checkpoint benchmark instances."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import author_extension_batch_01 as base  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]

base.SOURCE_ROOT = ROOT / "benchmark" / "source" / "extension_v1" / "batch_06"
base.CATALOG_VERSION = "0.3.5"
base.CATALOG_SOURCE = ROOT / "benchmark" / "catalog" / "snapshots" / "0.3.4"
base.CATALOG_TARGET = ROOT / "benchmark" / "catalog" / "snapshots" / base.CATALOG_VERSION
base.DESCRIPTOR_CONTEXT = "bounded event replay, checkpoint reconciliation, and audit workflows"
base.DESCRIPTOR_KEYWORDS = ["event", "checkpoint", "snapshot", "audit", "bounded_batch"]
base.DESCRIPTOR_SOURCE_REF = "extension-batch-06:event-checkpoint-curation"

base.TOPOLOGY_MAP.update(
    {
        "fan_in": "fan_out_fan_in",
        "windowed_batch": "sensor_gated",
        "branch_gate": "branch_merge",
    }
)

base.SERVICE_BY_STEP.update(
    {
        # Generic checkpoint/window services reused from Batch 05.
        "checkpoint_event_sort_deduplicator": ("checkpoint_event_sort_deduplicator", "Transformer"),
        "checkpoint_window_builder": ("checkpoint_window_builder", "Transformer"),
        "checkpoint_manifest_loader": ("checkpoint_manifest_loader", "Extractor"),
        "checkpoint_state_transition_applier": ("checkpoint_state_transition_applier", "Transformer"),
        "late_event_quarantine_writer": ("late_event_quarantine_writer", "Loader"),
        "checkpoint_route_outcome_merger": ("checkpoint_route_outcome_merger", "Aggregator"),
        "checkpoint_output_bundle_publisher": ("checkpoint_output_bundle_publisher", "Publisher"),
        # IoT snapshot transition services.
        "iot_device_event_batch_ingestor": ("iot_device_event_batch_ingestor", "Extractor"),
        "iot_device_registry_table_ingestor": ("iot_device_registry_table_ingestor", "Extractor"),
        "device_snapshot_checkpoint_loader": ("device_snapshot_checkpoint_loader", "Extractor"),
        "iot_snapshot_contract_validator": ("iot_snapshot_contract_validator", "QualityCheck"),
        "iot_device_event_snapshot_normalizer": ("iot_device_event_snapshot_normalizer", "Transformer"),
        "device_snapshot_state_transition_reconciler": ("device_snapshot_state_transition_reconciler", "Reconciler"),
        # Payment settlement reconciliation services.
        "settlement_event_batch_ingestor": ("settlement_event_batch_ingestor", "Extractor"),
        "bank_statement_table_ingestor": ("bank_statement_table_ingestor", "Extractor"),
        "settlement_checkpoint_loader": ("settlement_checkpoint_loader", "Extractor"),
        "settlement_reconciliation_contract_validator": (
            "settlement_reconciliation_contract_validator",
            "QualityCheck",
        ),
        "settlement_record_normalizer": ("settlement_record_normalizer", "Transformer"),
        "settlement_checkpoint_reconciler": ("settlement_checkpoint_reconciler", "Reconciler"),
        "settlement_exception_checkpoint_publisher": (
            "settlement_exception_checkpoint_publisher",
            "Publisher",
        ),
        # Notification and queue audit services.
        "notification_delivery_event_ingestor": ("notification_delivery_event_ingestor", "Extractor"),
        "notification_delivery_checkpoint_validator": (
            "notification_delivery_checkpoint_validator",
            "QualityCheck",
        ),
        "notification_delivery_audit_metric_computer": (
            "notification_delivery_audit_metric_computer",
            "Aggregator",
        ),
        "checkpoint_audit_bundle_publisher": ("checkpoint_audit_bundle_publisher", "Publisher"),
        "queue_snapshot_json_ingestor": ("queue_snapshot_json_ingestor", "Extractor"),
        "queue_capacity_checkpoint_validator": ("queue_capacity_checkpoint_validator", "QualityCheck"),
        "queue_backlog_capacity_risk_scorer": ("queue_backlog_capacity_risk_scorer", "ScoringService"),
        "checkpoint_alert_digest_publisher": ("checkpoint_alert_digest_publisher", "Publisher"),
        # Compliance replay services.
        "late_record_replay_batch_ingestor": ("late_record_replay_batch_ingestor", "Extractor"),
        "retention_policy_contract_validator": ("retention_policy_contract_validator", "QualityCheck"),
        "retention_policy_risk_decider": ("retention_policy_risk_decider", "DomainAdapter"),
        "compliance_approved_record_router": ("compliance_approved_record_router", "Publisher"),
        "compliance_exception_review_router": ("compliance_exception_review_router", "Publisher"),
        # Candidate distractors introduced with this batch.
        "checkpoint_position_only_loader": ("checkpoint_position_only_loader", "Extractor"),
        "append_only_event_archiver": ("append_only_event_archiver", "Loader"),
        "generic_queue_metric_counter": ("generic_queue_metric_counter", "Aggregator"),
        "audit_log_redaction_only_filter": ("audit_log_redaction_only_filter", "Transformer"),
    }
)

base.DISTRACTORS = [
    "checkpoint_position_only_loader",
    "checkpoint_event_sort_deduplicator",
    "append_only_event_archiver",
    "generic_queue_metric_counter",
    "audit_log_redaction_only_filter",
    "reviewed_domain_adapter",
]


PIPELINE_SERVICE_MAP: dict[str, dict[str, tuple[str, str]]] = {
    "iot_device_snapshot_transition": {
        "ingest_primary_source": ("iot_device_event_batch_ingestor", "Extractor"),
        "ingest_secondary_source": ("iot_device_registry_table_ingestor", "Extractor"),
        "ingest_reference_source": ("device_snapshot_checkpoint_loader", "Extractor"),
        "validate_source_contracts": ("iot_snapshot_contract_validator", "QualityCheck"),
        "normalize_sources": ("iot_device_event_snapshot_normalizer", "Transformer"),
        "fuse_sources": ("device_snapshot_state_transition_reconciler", "Reconciler"),
        "publish_outputs": ("checkpoint_output_bundle_publisher", "Publisher"),
    },
    "payment_settlement_checkpoint_reconcile": {
        "ingest_primary_source": ("settlement_event_batch_ingestor", "Extractor"),
        "ingest_secondary_source": ("bank_statement_table_ingestor", "Extractor"),
        "ingest_reference_source": ("settlement_checkpoint_loader", "Extractor"),
        "validate_source_contracts": ("settlement_reconciliation_contract_validator", "QualityCheck"),
        "normalize_sources": ("settlement_record_normalizer", "Transformer"),
        "fuse_sources": ("settlement_checkpoint_reconciler", "Reconciler"),
        "publish_outputs": ("settlement_exception_checkpoint_publisher", "Publisher"),
    },
    "notification_delivery_checkpoint_audit": {
        "ingest_bounded_events": ("notification_delivery_event_ingestor", "Extractor"),
        "validate_checkpoint_inputs": ("notification_delivery_checkpoint_validator", "QualityCheck"),
        "sort_and_deduplicate_records": ("checkpoint_event_sort_deduplicator", "Transformer"),
        "build_analysis_windows": ("checkpoint_window_builder", "Transformer"),
        "compute_window_metrics": ("notification_delivery_audit_metric_computer", "Aggregator"),
        "publish_outputs": ("checkpoint_audit_bundle_publisher", "Publisher"),
    },
    "queue_backlog_snapshot_analysis": {
        "ingest_bounded_events": ("queue_snapshot_json_ingestor", "Extractor"),
        "validate_checkpoint_inputs": ("queue_capacity_checkpoint_validator", "QualityCheck"),
        "sort_and_deduplicate_records": ("checkpoint_event_sort_deduplicator", "Transformer"),
        "build_analysis_windows": ("checkpoint_window_builder", "Transformer"),
        "compute_window_metrics": ("queue_backlog_capacity_risk_scorer", "ScoringService"),
        "publish_outputs": ("checkpoint_alert_digest_publisher", "Publisher"),
    },
    "late_record_replay_quarantine": {
        "ingest_source_batch": ("late_record_replay_batch_ingestor", "Extractor"),
        "validate_source_contract": ("retention_policy_contract_validator", "QualityCheck"),
        "load_previous_checkpoint": ("checkpoint_manifest_loader", "Extractor"),
        "apply_batch_to_checkpoint": ("checkpoint_state_transition_applier", "Transformer"),
        "quarantine_late_or_invalid_records": ("late_event_quarantine_writer", "Loader"),
        "evaluate_policy_or_risk": ("retention_policy_risk_decider", "DomainAdapter"),
        "route_approved_records": ("compliance_approved_record_router", "Publisher"),
        "route_exception_records": ("compliance_exception_review_router", "Publisher"),
        "merge_route_outcomes": ("checkpoint_route_outcome_merger", "Aggregator"),
        "publish_outputs": ("checkpoint_output_bundle_publisher", "Publisher"),
    },
}


def patched_write_instance(spec_path: Path, row: dict) -> dict:
    original = dict(base.SERVICE_BY_STEP)
    spec = base.load_json(spec_path)
    for step in spec["steps"]:
        base.SERVICE_BY_STEP[step["step_id"]] = PIPELINE_SERVICE_MAP[spec["pipeline_id"]][step["step_id"]]
    try:
        return base.write_instance(spec_path, row)
    finally:
        base.SERVICE_BY_STEP.clear()
        base.SERVICE_BY_STEP.update(original)


def update_review_file(reviews: list[dict]) -> None:
    review_dir = ROOT / "benchmark" / "catalog" / "review" / base.CATALOG_VERSION
    review_dir.mkdir(parents=True, exist_ok=True)
    existing_by_pipeline = {}
    source_review = ROOT / "benchmark" / "catalog" / "review" / "0.3.4" / "candidate_relationships.private.json"
    if source_review.exists():
        document = json.loads(source_review.read_text(encoding="utf-8"))
        existing_by_pipeline.update({item["pipeline_id"]: item for item in document.get("pipelines", [])})
    existing_by_pipeline.update({item["pipeline_id"]: item for item in reviews})
    (review_dir / "candidate_relationships.private.json").write_text(
        json.dumps(
            {
                "catalog_version": base.CATALOG_VERSION,
                "pipelines": [existing_by_pipeline[key] for key in sorted(existing_by_pipeline)],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    if not base.CATALOG_SOURCE.exists():
        raise FileNotFoundError("Batch 06 requires catalog snapshot 0.3.4 from Batch 05")
    base.prepare_catalogue()
    rows = base.manifest_rows()
    reviews = []
    pipelines = []
    for spec_path in sorted((base.SOURCE_ROOT / "specs").glob("*.json")):
        spec = base.load_json(spec_path)
        pipelines.append(spec["pipeline_id"])
        reviews.append(patched_write_instance(spec_path, rows[spec["pipeline_id"]]))
    base.update_manifest_statuses(pipelines)
    update_review_file(reviews)
    for pipeline in pipelines:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_instance.py"), str(base.INSTANCE_ROOT / pipeline)],
            cwd=ROOT,
            check=True,
        )
    print("authored extension batch 06: 5 instances and catalogue 0.3.5")


if __name__ == "__main__":
    main()
