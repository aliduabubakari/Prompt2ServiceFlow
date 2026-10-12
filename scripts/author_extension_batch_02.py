#!/usr/bin/env python3
"""Author Extension-50 batch 02 as reviewed multimodal benchmark instances."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import author_extension_batch_01 as base  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]

base.SOURCE_ROOT = ROOT / "benchmark" / "source" / "extension_v1" / "batch_02"
base.CATALOG_VERSION = "0.3.1"
base.CATALOG_SOURCE = ROOT / "benchmark" / "catalog" / "snapshots" / "0.3.0"
base.CATALOG_TARGET = ROOT / "benchmark" / "catalog" / "snapshots" / base.CATALOG_VERSION

base.TOPOLOGY_MAP.update(
    {
        "fan_in": "fan_out_fan_in",
        "fan_out_fan_in": "fan_out_fan_in",
    }
)

base.SERVICE_BY_STEP.update(
    {
        "ingest_primary_source": ("multimodal_primary_source_ingestor", "Extractor"),
        "ingest_secondary_source": ("multimodal_secondary_source_ingestor", "Extractor"),
        "ingest_reference_source": ("multimodal_reference_source_ingestor", "Extractor"),
        "validate_source_contracts": ("multimodal_multi_source_contract_validator", "QualityCheck"),
        "normalize_sources": ("multimodal_multi_source_normalizer", "Transformer"),
        "fuse_sources": ("multimodal_source_fusion_reconciler", "Reconciler"),
        "normalize_partition_a": ("multimodal_partition_a_normalizer", "Transformer"),
        "normalize_partition_b": ("multimodal_partition_b_normalizer", "Transformer"),
        "normalize_partition_c": ("multimodal_partition_c_normalizer", "Transformer"),
        "fuse_partitions": ("multimodal_partition_fusion_aggregator", "Aggregator"),
    }
)


def update_review_file(reviews: list[dict]) -> None:
    review_dir = ROOT / "benchmark" / "catalog" / "review" / base.CATALOG_VERSION
    review_dir.mkdir(parents=True, exist_ok=True)
    review_path = review_dir / "candidate_relationships.private.json"
    existing_by_pipeline = {}
    source_review = ROOT / "benchmark" / "catalog" / "review" / "0.3.0" / "candidate_relationships.private.json"
    if source_review.exists():
        document = json.loads(source_review.read_text(encoding="utf-8"))
        existing_by_pipeline.update({item["pipeline_id"]: item for item in document.get("pipelines", [])})
    if review_path.exists():
        document = json.loads(review_path.read_text(encoding="utf-8"))
        existing_by_pipeline.update({item["pipeline_id"]: item for item in document.get("pipelines", [])})
    existing_by_pipeline.update({item["pipeline_id"]: item for item in reviews})
    review_path.write_text(
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
        raise FileNotFoundError("Batch 02 requires catalog snapshot 0.3.0 from Batch 01")
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
    print("authored extension batch 02: 5 instances and catalogue 0.3.1")


if __name__ == "__main__":
    main()
