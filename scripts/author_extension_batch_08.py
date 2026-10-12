#!/usr/bin/env python3
"""Author Extension-50 batch 08 complex mixed-domain instances."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import author_extension_batch_01 as base  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]

base.SOURCE_ROOT = ROOT / "benchmark" / "source" / "extension_v1" / "batch_08"
base.CATALOG_VERSION = "0.3.7"
base.CATALOG_SOURCE = ROOT / "benchmark" / "catalog" / "snapshots" / "0.3.6"
base.CATALOG_TARGET = ROOT / "benchmark" / "catalog" / "snapshots" / base.CATALOG_VERSION
base.DESCRIPTOR_CONTEXT = "complex mixed-domain data fusion, routing, publication, and review workflows"
base.DESCRIPTOR_KEYWORDS = ["mixed_domain", "fusion", "routing", "priority", "publication"]
base.DESCRIPTOR_SOURCE_REF = "extension-batch-08:complex-mixed-domain-curation"

base.TOPOLOGY_MAP.update(
    {
        "fan_out_fan_in": "fan_out_fan_in",
        "branch_gate": "branch_merge",
    }
)

base.SERVICE_BY_STEP.update(
    {
        # Shared mixed-domain services.
        "mixed_domain_entity_standardizer": ("mixed_domain_entity_standardizer", "Transformer"),
        "cross_modal_entity_conflict_resolver": ("cross_modal_entity_conflict_resolver", "Reconciler"),
        "mixed_domain_route_outcome_merger": ("mixed_domain_route_outcome_merger", "Aggregator"),
        "mixed_domain_completion_bundle_publisher": (
            "mixed_domain_completion_bundle_publisher",
            "Publisher",
        ),
        # Disaster response services.
        "disaster_multimodal_batch_ingestor": ("disaster_multimodal_batch_ingestor", "Extractor"),
        "disaster_response_contract_validator": ("disaster_response_contract_validator", "QualityCheck"),
        "disaster_imagery_partition_normalizer": (
            "disaster_imagery_partition_normalizer",
            "Transformer",
        ),
        "disaster_shelter_status_normalizer": ("disaster_shelter_status_normalizer", "Transformer"),
        "disaster_road_incident_text_normalizer": (
            "disaster_road_incident_text_normalizer",
            "Transformer",
        ),
        "disaster_operational_picture_fuser": ("disaster_operational_picture_fuser", "Integrator"),
        "disaster_operational_priority_scorer": (
            "disaster_operational_priority_scorer",
            "ScoringService",
        ),
        "disaster_routing_gate_evaluator": ("disaster_routing_gate_evaluator", "DomainAdapter"),
        "disaster_briefing_packet_builder": ("disaster_briefing_packet_builder", "Aggregator"),
        "disaster_notification_publisher": ("disaster_notification_publisher", "Publisher"),
        "disaster_response_bundle_publisher": ("disaster_response_bundle_publisher", "Publisher"),
        # Smart city services.
        "smart_city_incident_batch_ingestor": ("smart_city_incident_batch_ingestor", "Extractor"),
        "smart_city_contract_validator": ("smart_city_contract_validator", "QualityCheck"),
        "citizen_report_partition_normalizer": ("citizen_report_partition_normalizer", "Transformer"),
        "street_image_partition_normalizer": ("street_image_partition_normalizer", "Transformer"),
        "sensor_asset_partition_normalizer": ("sensor_asset_partition_normalizer", "Transformer"),
        "smart_city_incident_context_fuser": ("smart_city_incident_context_fuser", "Integrator"),
        "smart_city_incident_priority_scorer": (
            "smart_city_incident_priority_scorer",
            "ScoringService",
        ),
        "smart_city_work_order_publisher": ("smart_city_work_order_publisher", "Publisher"),
        # Supply-chain services.
        "supply_chain_disruption_batch_ingestor": (
            "supply_chain_disruption_batch_ingestor",
            "Extractor",
        ),
        "supply_chain_contract_validator": ("supply_chain_contract_validator", "QualityCheck"),
        "shipment_status_partition_normalizer": (
            "shipment_status_partition_normalizer",
            "Transformer",
        ),
        "supplier_capacity_partition_normalizer": (
            "supplier_capacity_partition_normalizer",
            "Transformer",
        ),
        "external_alert_partition_normalizer": (
            "external_alert_partition_normalizer",
            "Transformer",
        ),
        "supply_chain_disruption_context_fuser": (
            "supply_chain_disruption_context_fuser",
            "Integrator",
        ),
        "supply_chain_disruption_priority_scorer": (
            "supply_chain_disruption_priority_scorer",
            "ScoringService",
        ),
        "supply_chain_response_bundle_publisher": (
            "supply_chain_response_bundle_publisher",
            "Publisher",
        ),
        # Research publication services.
        "research_publication_batch_ingestor": (
            "research_publication_batch_ingestor",
            "Extractor",
        ),
        "research_publication_contract_validator": (
            "research_publication_contract_validator",
            "QualityCheck",
        ),
        "research_package_priority_scorer": ("research_package_priority_scorer", "ScoringService"),
        "research_publication_gate_evaluator": (
            "research_publication_gate_evaluator",
            "DomainAdapter",
        ),
        "research_publication_packet_builder": (
            "research_publication_packet_builder",
            "Aggregator",
        ),
        "research_publication_notification_publisher": (
            "research_publication_notification_publisher",
            "Publisher",
        ),
        "research_publication_policy_decider": (
            "research_publication_policy_decider",
            "DomainAdapter",
        ),
        "research_publication_approved_router": (
            "research_publication_approved_router",
            "Publisher",
        ),
        "research_publication_exception_router": (
            "research_publication_exception_router",
            "Publisher",
        ),
        # Public benefits services.
        "benefits_case_batch_ingestor": ("benefits_case_batch_ingestor", "Extractor"),
        "benefits_case_contract_validator": ("benefits_case_contract_validator", "QualityCheck"),
        "benefits_case_priority_scorer": ("benefits_case_priority_scorer", "ScoringService"),
        "benefits_eligibility_policy_decider": (
            "benefits_eligibility_policy_decider",
            "DomainAdapter",
        ),
        "benefits_approved_notification_router": (
            "benefits_approved_notification_router",
            "Publisher",
        ),
        "benefits_case_review_router": ("benefits_case_review_router", "Publisher"),
        # Candidate distractors.
        "generic_multimodal_bundle_ingestor": ("generic_multimodal_bundle_ingestor", "Extractor"),
        "single_source_priority_ranker": ("single_source_priority_ranker", "ScoringService"),
        "geojson_format_converter_only": ("geojson_format_converter_only", "Transformer"),
        "notification_only_publisher": ("notification_only_publisher", "Publisher"),
        "publication_manifest_archiver": ("publication_manifest_archiver", "Loader"),
    }
)

base.DISTRACTORS = [
    "generic_multimodal_bundle_ingestor",
    "single_source_priority_ranker",
    "geojson_format_converter_only",
    "notification_only_publisher",
    "publication_manifest_archiver",
    "reviewed_domain_adapter",
]


PIPELINE_SERVICE_MAP: dict[str, dict[str, tuple[str, str]]] = {
    "disaster_response_data_fusion": {
        "ingest_source_batch": ("disaster_multimodal_batch_ingestor", "Extractor"),
        "validate_source_contract": ("disaster_response_contract_validator", "QualityCheck"),
        "normalize_partition_a": ("disaster_imagery_partition_normalizer", "Transformer"),
        "normalize_partition_b": ("disaster_shelter_status_normalizer", "Transformer"),
        "normalize_partition_c": ("disaster_road_incident_text_normalizer", "Transformer"),
        "fuse_partitions": ("disaster_operational_picture_fuser", "Integrator"),
        "standardize_cross_domain_entities": ("mixed_domain_entity_standardizer", "Transformer"),
        "resolve_entity_conflicts": ("cross_modal_entity_conflict_resolver", "Reconciler"),
        "score_operational_priority": ("disaster_operational_priority_scorer", "ScoringService"),
        "apply_publication_or_routing_gate": ("disaster_routing_gate_evaluator", "DomainAdapter"),
        "create_stakeholder_packet": ("disaster_briefing_packet_builder", "Aggregator"),
        "publish_notifications": ("disaster_notification_publisher", "Publisher"),
        "publish_outputs": ("disaster_response_bundle_publisher", "Publisher"),
    },
    "smart_city_incident_routing": {
        "ingest_source_batch": ("smart_city_incident_batch_ingestor", "Extractor"),
        "validate_source_contract": ("smart_city_contract_validator", "QualityCheck"),
        "normalize_partition_a": ("citizen_report_partition_normalizer", "Transformer"),
        "normalize_partition_b": ("street_image_partition_normalizer", "Transformer"),
        "normalize_partition_c": ("sensor_asset_partition_normalizer", "Transformer"),
        "fuse_partitions": ("smart_city_incident_context_fuser", "Integrator"),
        "standardize_cross_domain_entities": ("mixed_domain_entity_standardizer", "Transformer"),
        "resolve_entity_conflicts": ("cross_modal_entity_conflict_resolver", "Reconciler"),
        "score_operational_priority": ("smart_city_incident_priority_scorer", "ScoringService"),
        "publish_outputs": ("smart_city_work_order_publisher", "Publisher"),
    },
    "supply_chain_disruption_triage": {
        "ingest_source_batch": ("supply_chain_disruption_batch_ingestor", "Extractor"),
        "validate_source_contract": ("supply_chain_contract_validator", "QualityCheck"),
        "normalize_partition_a": ("shipment_status_partition_normalizer", "Transformer"),
        "normalize_partition_b": ("supplier_capacity_partition_normalizer", "Transformer"),
        "normalize_partition_c": ("external_alert_partition_normalizer", "Transformer"),
        "fuse_partitions": ("supply_chain_disruption_context_fuser", "Integrator"),
        "standardize_cross_domain_entities": ("mixed_domain_entity_standardizer", "Transformer"),
        "resolve_entity_conflicts": ("cross_modal_entity_conflict_resolver", "Reconciler"),
        "score_operational_priority": ("supply_chain_disruption_priority_scorer", "ScoringService"),
        "publish_outputs": ("supply_chain_response_bundle_publisher", "Publisher"),
    },
    "research_data_lake_publication_gate": {
        "ingest_source_batch": ("research_publication_batch_ingestor", "Extractor"),
        "validate_source_contract": ("research_publication_contract_validator", "QualityCheck"),
        "standardize_cross_domain_entities": ("mixed_domain_entity_standardizer", "Transformer"),
        "resolve_entity_conflicts": ("cross_modal_entity_conflict_resolver", "Reconciler"),
        "score_operational_priority": ("research_package_priority_scorer", "ScoringService"),
        "apply_publication_or_routing_gate": ("research_publication_gate_evaluator", "DomainAdapter"),
        "create_stakeholder_packet": ("research_publication_packet_builder", "Aggregator"),
        "publish_notifications": ("research_publication_notification_publisher", "Publisher"),
        "evaluate_policy_or_risk": ("research_publication_policy_decider", "DomainAdapter"),
        "route_approved_records": ("research_publication_approved_router", "Publisher"),
        "route_exception_records": ("research_publication_exception_router", "Publisher"),
        "merge_route_outcomes": ("mixed_domain_route_outcome_merger", "Aggregator"),
        "publish_outputs": ("mixed_domain_completion_bundle_publisher", "Publisher"),
    },
    "public_benefits_case_review_notification": {
        "ingest_source_batch": ("benefits_case_batch_ingestor", "Extractor"),
        "validate_source_contract": ("benefits_case_contract_validator", "QualityCheck"),
        "standardize_cross_domain_entities": ("mixed_domain_entity_standardizer", "Transformer"),
        "resolve_entity_conflicts": ("cross_modal_entity_conflict_resolver", "Reconciler"),
        "score_operational_priority": ("benefits_case_priority_scorer", "ScoringService"),
        "evaluate_policy_or_risk": ("benefits_eligibility_policy_decider", "DomainAdapter"),
        "route_approved_records": ("benefits_approved_notification_router", "Publisher"),
        "route_exception_records": ("benefits_case_review_router", "Publisher"),
        "merge_route_outcomes": ("mixed_domain_route_outcome_merger", "Aggregator"),
        "publish_outputs": ("mixed_domain_completion_bundle_publisher", "Publisher"),
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
    source_review = ROOT / "benchmark" / "catalog" / "review" / "0.3.6" / "candidate_relationships.private.json"
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
        raise FileNotFoundError("Batch 08 requires catalog snapshot 0.3.6 from Batch 07")
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
    print("authored extension batch 08: 5 instances and catalogue 0.3.7")


if __name__ == "__main__":
    main()
