#!/usr/bin/env python3
"""Author Extension-50 batch 03 as reviewed API/JSON + table fusion instances."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import author_extension_batch_01 as base  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]

base.SOURCE_ROOT = ROOT / "benchmark" / "source" / "extension_v1" / "batch_03"
base.CATALOG_VERSION = "0.3.2"
base.CATALOG_SOURCE = ROOT / "benchmark" / "catalog" / "snapshots" / "0.3.1"
base.CATALOG_TARGET = ROOT / "benchmark" / "catalog" / "snapshots" / base.CATALOG_VERSION
base.DESCRIPTOR_CONTEXT = "bounded API/JSON and tabular fusion batches"
base.DESCRIPTOR_KEYWORDS = ["api", "json", "table", "fusion", "reconciliation"]
base.DESCRIPTOR_SOURCE_REF = "extension-batch-03:api-table-fusion-curation"

base.TOPOLOGY_MAP.update(
    {
        "fan_in": "fan_out_fan_in",
        "branch_gate": "branch_merge",
        "staged": "staged_etl",
    }
)

base.SERVICE_BY_STEP.update(
    {
        "ingest_primary_source": ("api_table_primary_source_ingestor", "Extractor"),
        "ingest_secondary_source": ("api_table_secondary_source_ingestor", "Extractor"),
        "ingest_reference_source": ("api_table_reference_source_ingestor", "Extractor"),
        "validate_source_contracts": ("api_table_multi_source_contract_validator", "QualityCheck"),
        "normalize_sources": ("api_table_multi_source_normalizer", "Transformer"),
        "fuse_sources": ("api_table_source_fusion_reconciler", "Reconciler"),
        "ingest_source_batch": ("api_table_source_bundle_ingestor", "Extractor"),
        "validate_source_contract": ("api_table_source_contract_validator", "QualityCheck"),
        "stage_raw_artifacts": ("api_table_raw_artifact_stager", "Loader"),
        "normalize_records": ("api_table_record_normalizer", "Transformer"),
        "flatten_nested_payloads": ("nested_json_payload_flattener", "Transformer"),
        "join_tabular_reference_data": ("api_table_reference_joiner", "Integrator"),
        "reconcile_conflicting_values": ("api_table_conflict_reconciler", "Reconciler"),
        "evaluate_policy_or_risk": ("api_table_policy_risk_decider", "DomainAdapter"),
        "route_approved_records": ("api_table_approved_record_router", "Publisher"),
        "route_exception_records": ("api_table_exception_review_router", "Publisher"),
        "merge_route_outcomes": ("api_table_route_outcome_merger", "Aggregator"),
        "publish_outputs": ("api_table_output_bundle_publisher", "Publisher"),
    }
)

base.DISTRACTORS = [
    "reviewed_domain_adapter",
    "json_field_projection_transformer",
    "csv_to_structured_json_standardizer",
    "customer_profile_field_normalizer",
    "federated_entity_matcher",
    "discrepancy_route_decider",
]


def update_review_file(reviews: list[dict]) -> None:
    review_dir = ROOT / "benchmark" / "catalog" / "review" / base.CATALOG_VERSION
    review_dir.mkdir(parents=True, exist_ok=True)
    existing_by_pipeline = {}
    source_review = ROOT / "benchmark" / "catalog" / "review" / "0.3.1" / "candidate_relationships.private.json"
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
        raise FileNotFoundError("Batch 03 requires catalog snapshot 0.3.1 from Batch 02")
    base.prepare_catalogue()
    rows = base.manifest_rows()
    reviews = []
    pipelines = []
    for spec_path in sorted((base.SOURCE_ROOT / "specs").glob("*.json")):
        spec = base.load_json(spec_path)
        pipelines.append(spec["pipeline_id"])
        reviews.append(base.write_instance(spec_path, rows[spec["pipeline_id"]]))
    base.update_manifest_statuses(pipelines)
    update_review_file(reviews)
    for pipeline in pipelines:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_instance.py"), str(base.INSTANCE_ROOT / pipeline)],
            cwd=ROOT,
            check=True,
        )
    print("authored extension batch 03: 5 instances and catalogue 0.3.2")


if __name__ == "__main__":
    main()
