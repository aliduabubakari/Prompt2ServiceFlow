#!/usr/bin/env python3
"""Author Extension-50 batch 05 time-series and event/checkpoint instances."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import author_extension_batch_01 as base  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]

base.SOURCE_ROOT = ROOT / "benchmark" / "source" / "extension_v1" / "batch_05"
base.CATALOG_VERSION = "0.3.4"
base.CATALOG_SOURCE = ROOT / "benchmark" / "catalog" / "snapshots" / "0.3.3"
base.CATALOG_TARGET = ROOT / "benchmark" / "catalog" / "snapshots" / base.CATALOG_VERSION
base.DESCRIPTOR_CONTEXT = "bounded time-series, event replay, and checkpointed batch workflows"
base.DESCRIPTOR_KEYWORDS = ["time_series", "event", "checkpoint", "window", "bounded_batch"]
base.DESCRIPTOR_SOURCE_REF = "extension-batch-05:time-series-event-checkpoint-curation"

base.TOPOLOGY_MAP.update(
    {
        "fan_in": "fan_out_fan_in",
        "windowed_batch": "sensor_gated",
        "branch_gate": "branch_merge",
    }
)

base.SERVICE_BY_STEP.update(
    {
        # Time-series/window services from Batch 04.
        "ingest_bounded_events": ("bounded_timeseries_event_ingestor", "Extractor"),
        "validate_checkpoint_inputs": ("bounded_window_checkpoint_validator", "QualityCheck"),
        "sort_and_deduplicate_records": ("timeseries_record_sort_deduplicator", "Transformer"),
        "build_analysis_windows": ("bounded_analysis_window_builder", "Transformer"),
        "compute_window_metrics": ("window_metric_aggregator", "Aggregator"),
        "align_time_index": ("timeseries_index_alignment_transformer", "Transformer"),
        "ingest_primary_source": ("timeseries_primary_source_ingestor", "Extractor"),
        "ingest_secondary_source": ("timeseries_secondary_source_ingestor", "Extractor"),
        "ingest_reference_source": ("timeseries_reference_source_ingestor", "Extractor"),
        "validate_source_contracts": ("timeseries_multi_source_contract_validator", "QualityCheck"),
        "normalize_sources": ("timeseries_multi_source_normalizer", "Transformer"),
        "fuse_sources": ("timeseries_source_fusion_reconciler", "Reconciler"),
        # Event/checkpoint additions.
        "ingest_source_batch": ("checkpoint_event_batch_ingestor", "Extractor"),
        "validate_source_contract": ("checkpoint_event_contract_validator", "QualityCheck"),
        "checkpoint_bounded_event_ingestor": ("checkpoint_bounded_event_ingestor", "Extractor"),
        "checkpoint_boundary_validator": ("checkpoint_boundary_validator", "QualityCheck"),
        "checkpoint_event_sort_deduplicator": ("checkpoint_event_sort_deduplicator", "Transformer"),
        "checkpoint_window_builder": ("checkpoint_window_builder", "Transformer"),
        "checkpoint_window_metric_computer": ("checkpoint_window_metric_computer", "Aggregator"),
        "load_previous_checkpoint": ("checkpoint_manifest_loader", "Extractor"),
        "apply_batch_to_checkpoint": ("checkpoint_state_transition_applier", "Transformer"),
        "quarantine_late_or_invalid_records": ("late_event_quarantine_writer", "Loader"),
        "evaluate_policy_or_risk": ("checkpoint_event_policy_risk_decider", "DomainAdapter"),
        "route_approved_records": ("checkpoint_approved_record_router", "Publisher"),
        "route_exception_records": ("checkpoint_exception_review_router", "Publisher"),
        "merge_route_outcomes": ("checkpoint_route_outcome_merger", "Aggregator"),
        "publish_outputs": ("checkpoint_output_bundle_publisher", "Publisher"),
    }
)

base.DISTRACTORS = [
    "reviewed_domain_adapter",
    "bounded_window_checkpoint_validator",
    "event_record_cleaner",
    "external_workflow_completion_sensor",
    "iot_anomaly_feature_calculator",
    "dataset_quarantine_zone_writer",
]


def service_for_step(step_id: str, pipeline_id: str) -> tuple[str, str]:
    if pipeline_id in {"observability_metrics_incident_digest", "climate_station_gap_fill_alignment"}:
        time_services = {
            "ingest_bounded_events": ("bounded_timeseries_event_ingestor", "Extractor"),
            "validate_checkpoint_inputs": ("bounded_window_checkpoint_validator", "QualityCheck"),
            "sort_and_deduplicate_records": ("timeseries_record_sort_deduplicator", "Transformer"),
            "build_analysis_windows": ("bounded_analysis_window_builder", "Transformer"),
            "compute_window_metrics": ("window_metric_aggregator", "Aggregator"),
            "align_time_index": ("timeseries_index_alignment_transformer", "Transformer"),
            "ingest_primary_source": ("timeseries_primary_source_ingestor", "Extractor"),
            "ingest_secondary_source": ("timeseries_secondary_source_ingestor", "Extractor"),
            "ingest_reference_source": ("timeseries_reference_source_ingestor", "Extractor"),
            "validate_source_contracts": ("timeseries_multi_source_contract_validator", "QualityCheck"),
            "normalize_sources": ("timeseries_multi_source_normalizer", "Transformer"),
            "fuse_sources": ("timeseries_source_fusion_reconciler", "Reconciler"),
            "publish_outputs": ("timeseries_output_bundle_publisher", "Publisher"),
        }
        return time_services[step_id]
    event_services = {
        "ingest_bounded_events": ("checkpoint_bounded_event_ingestor", "Extractor"),
        "validate_checkpoint_inputs": ("checkpoint_boundary_validator", "QualityCheck"),
        "sort_and_deduplicate_records": ("checkpoint_event_sort_deduplicator", "Transformer"),
        "build_analysis_windows": ("checkpoint_window_builder", "Transformer"),
        "compute_window_metrics": ("checkpoint_window_metric_computer", "Aggregator"),
        "load_previous_checkpoint": ("checkpoint_manifest_loader", "Extractor"),
        "ingest_source_batch": ("checkpoint_event_batch_ingestor", "Extractor"),
        "validate_source_contract": ("checkpoint_event_contract_validator", "QualityCheck"),
        "apply_batch_to_checkpoint": ("checkpoint_state_transition_applier", "Transformer"),
        "quarantine_late_or_invalid_records": ("late_event_quarantine_writer", "Loader"),
        "evaluate_policy_or_risk": ("checkpoint_event_policy_risk_decider", "DomainAdapter"),
        "route_approved_records": ("checkpoint_approved_record_router", "Publisher"),
        "route_exception_records": ("checkpoint_exception_review_router", "Publisher"),
        "merge_route_outcomes": ("checkpoint_route_outcome_merger", "Aggregator"),
        "publish_outputs": ("checkpoint_output_bundle_publisher", "Publisher"),
    }
    return event_services[step_id]


def patched_write_instance(spec_path: Path, row: dict) -> dict:
    original = dict(base.SERVICE_BY_STEP)
    spec = base.load_json(spec_path)
    for step in spec["steps"]:
        base.SERVICE_BY_STEP[step["step_id"]] = service_for_step(step["step_id"], spec["pipeline_id"])
    try:
        return base.write_instance(spec_path, row)
    finally:
        base.SERVICE_BY_STEP.clear()
        base.SERVICE_BY_STEP.update(original)


def update_review_file(reviews: list[dict]) -> None:
    review_dir = ROOT / "benchmark" / "catalog" / "review" / base.CATALOG_VERSION
    review_dir.mkdir(parents=True, exist_ok=True)
    existing_by_pipeline = {}
    source_review = ROOT / "benchmark" / "catalog" / "review" / "0.3.3" / "candidate_relationships.private.json"
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
        raise FileNotFoundError("Batch 05 requires catalog snapshot 0.3.3 from Batch 04")
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
    print("authored extension batch 05: 5 instances and catalogue 0.3.4")


if __name__ == "__main__":
    main()
