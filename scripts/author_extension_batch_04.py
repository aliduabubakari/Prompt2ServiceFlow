#!/usr/bin/env python3
"""Author Extension-50 batch 04 mixed API/table and time-series/window instances."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import author_extension_batch_01 as base  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]

base.SOURCE_ROOT = ROOT / "benchmark" / "source" / "extension_v1" / "batch_04"
base.CATALOG_VERSION = "0.3.3"
base.CATALOG_SOURCE = ROOT / "benchmark" / "catalog" / "snapshots" / "0.3.2"
base.CATALOG_TARGET = ROOT / "benchmark" / "catalog" / "snapshots" / base.CATALOG_VERSION
base.DESCRIPTOR_CONTEXT = "bounded API/table and time-series/window batch workflows"
base.DESCRIPTOR_KEYWORDS = ["api", "json", "table", "time_series", "window", "sensor"]
base.DESCRIPTOR_SOURCE_REF = "extension-batch-04:mixed-api-time-series-curation"

base.TOPOLOGY_MAP.update(
    {
        "fan_in": "fan_out_fan_in",
        "fan_out": "fan_out",
        "windowed_batch": "sensor_gated",
    }
)

base.SERVICE_BY_STEP.update(
    {
        # API/table fusion carry-over for support_profile_context_join.
        "ingest_primary_source": ("api_table_primary_source_ingestor", "Extractor"),
        "ingest_secondary_source": ("api_table_secondary_source_ingestor", "Extractor"),
        "ingest_reference_source": ("api_table_reference_source_ingestor", "Extractor"),
        "validate_source_contracts": ("api_table_multi_source_contract_validator", "QualityCheck"),
        "normalize_sources": ("api_table_multi_source_normalizer", "Transformer"),
        "fuse_sources": ("api_table_source_fusion_reconciler", "Reconciler"),
        # Time-series/window source shapes.
        "ingest_bounded_events": ("bounded_timeseries_event_ingestor", "Extractor"),
        "validate_checkpoint_inputs": ("bounded_window_checkpoint_validator", "QualityCheck"),
        "sort_and_deduplicate_records": ("timeseries_record_sort_deduplicator", "Transformer"),
        "build_analysis_windows": ("bounded_analysis_window_builder", "Transformer"),
        "compute_window_metrics": ("window_metric_aggregator", "Aggregator"),
        "align_time_index": ("timeseries_index_alignment_transformer", "Transformer"),
        "fill_small_gaps": ("timeseries_gap_fill_quality_transformer", "Transformer"),
        "detect_window_anomalies": ("timeseries_window_anomaly_detector", "ScoringService"),
        # Fan-out telemetry quality shape.
        "ingest_source_batch": ("timeseries_source_bundle_ingestor", "Extractor"),
        "validate_source_contract": ("timeseries_source_contract_validator", "QualityCheck"),
        "extract_branch_features": ("timeseries_branch_feature_extractor", "Extractor"),
        "enrich_branch_context": ("timeseries_context_enricher", "Integrator"),
        "score_branch_quality": ("timeseries_quality_scorer", "ScoringService"),
        "merge_branch_outputs": ("timeseries_branch_output_merger", "Aggregator"),
        "publish_outputs": ("timeseries_output_bundle_publisher", "Publisher"),
    }
)

base.DISTRACTORS = [
    "reviewed_domain_adapter",
    "sensor_window_alignment_fuser",
    "iot_anomaly_feature_calculator",
    "event_record_cleaner",
    "feature_table_drift_validator",
    "api_table_conflict_reconciler",
]


def service_for_step(step_id: str, pipeline_id: str) -> tuple[str, str]:
    if pipeline_id == "support_profile_context_join":
        api_services = {
            "ingest_primary_source": ("api_table_primary_source_ingestor", "Extractor"),
            "ingest_secondary_source": ("api_table_secondary_source_ingestor", "Extractor"),
            "ingest_reference_source": ("api_table_reference_source_ingestor", "Extractor"),
            "validate_source_contracts": ("api_table_multi_source_contract_validator", "QualityCheck"),
            "normalize_sources": ("api_table_multi_source_normalizer", "Transformer"),
            "fuse_sources": ("api_table_source_fusion_reconciler", "Reconciler"),
            "publish_outputs": ("api_table_output_bundle_publisher", "Publisher"),
        }
        return api_services[step_id]
    return base.SERVICE_BY_STEP[step_id]


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
    source_review = ROOT / "benchmark" / "catalog" / "review" / "0.3.2" / "candidate_relationships.private.json"
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
        raise FileNotFoundError("Batch 04 requires catalog snapshot 0.3.2 from Batch 03")
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
    print("authored extension batch 04: 5 instances and catalogue 0.3.3")


if __name__ == "__main__":
    main()
