#!/usr/bin/env python3
"""Author Extension-50 batch 07 policy/privacy/human-review instances."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import author_extension_batch_01 as base  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]

base.SOURCE_ROOT = ROOT / "benchmark" / "source" / "extension_v1" / "batch_07"
base.CATALOG_VERSION = "0.3.6"
base.CATALOG_SOURCE = ROOT / "benchmark" / "catalog" / "snapshots" / "0.3.5"
base.CATALOG_TARGET = ROOT / "benchmark" / "catalog" / "snapshots" / base.CATALOG_VERSION
base.DESCRIPTOR_CONTEXT = "bounded policy, privacy, redaction, and human-review workflows"
base.DESCRIPTOR_KEYWORDS = ["policy", "privacy", "redaction", "human_review", "audit"]
base.DESCRIPTOR_SOURCE_REF = "extension-batch-07:policy-privacy-human-review-curation"

base.TOPOLOGY_MAP.update(
    {
        "fan_in": "fan_out_fan_in",
        "branch_gate": "branch_merge",
    }
)

base.SERVICE_BY_STEP.update(
    {
        # Shared policy-review services.
        "policy_route_outcome_merger": ("policy_route_outcome_merger", "Aggregator"),
        "policy_review_bundle_publisher": ("policy_review_bundle_publisher", "Publisher"),
        "policy_decision_audit_recorder": ("policy_decision_audit_recorder", "Loader"),
        "policy_audit_log_writer": ("policy_audit_log_writer", "Loader"),
        "reviewer_notification_publisher": ("reviewer_notification_publisher", "Publisher"),
        # Clinical note PHI services.
        "clinical_note_batch_ingestor": ("clinical_note_batch_ingestor", "Extractor"),
        "clinical_phi_contract_validator": ("clinical_phi_contract_validator", "QualityCheck"),
        "clinical_phi_detector": ("clinical_phi_detector", "DomainAdapter"),
        "clinical_note_redaction_transformer": ("clinical_note_redaction_transformer", "Transformer"),
        "clinical_phi_review_packet_builder": ("clinical_phi_review_packet_builder", "Aggregator"),
        "clinical_phi_policy_risk_decider": ("clinical_phi_policy_risk_decider", "DomainAdapter"),
        "clinical_phi_release_router": ("clinical_phi_release_router", "Publisher"),
        "clinical_phi_review_queue_router": ("clinical_phi_review_queue_router", "Publisher"),
        # Financial escalation services.
        "transaction_policy_batch_ingestor": ("transaction_policy_batch_ingestor", "Extractor"),
        "transaction_escalation_contract_validator": (
            "transaction_escalation_contract_validator",
            "QualityCheck",
        ),
        "transaction_sensitive_field_detector": ("transaction_sensitive_field_detector", "DomainAdapter"),
        "transaction_minimization_transformer": ("transaction_minimization_transformer", "Transformer"),
        "transaction_escalation_packet_builder": ("transaction_escalation_packet_builder", "Aggregator"),
        "transaction_escalation_policy_decider": ("transaction_escalation_policy_decider", "DomainAdapter"),
        "transaction_low_risk_status_router": ("transaction_low_risk_status_router", "Publisher"),
        "transaction_case_review_router": ("transaction_case_review_router", "Publisher"),
        # Student privacy services.
        "student_record_privacy_batch_ingestor": ("student_record_privacy_batch_ingestor", "Extractor"),
        "student_privacy_contract_validator": ("student_privacy_contract_validator", "QualityCheck"),
        "student_research_release_policy_decider": (
            "student_research_release_policy_decider",
            "DomainAdapter",
        ),
        "student_redacted_release_router": ("student_redacted_release_router", "Publisher"),
        "student_steward_review_router": ("student_steward_review_router", "Publisher"),
        # Access entitlement fan-in services.
        "identity_provider_export_ingestor": ("identity_provider_export_ingestor", "Extractor"),
        "resource_entitlement_table_ingestor": ("resource_entitlement_table_ingestor", "Extractor"),
        "manager_directory_reference_ingestor": ("manager_directory_reference_ingestor", "Extractor"),
        "entitlement_recertification_contract_validator": (
            "entitlement_recertification_contract_validator",
            "QualityCheck",
        ),
        "entitlement_identity_normalizer": ("entitlement_identity_normalizer", "Transformer"),
        "entitlement_identity_resource_fuser": ("entitlement_identity_resource_fuser", "Integrator"),
        "entitlement_sensitive_attribute_detector": (
            "entitlement_sensitive_attribute_detector",
            "DomainAdapter",
        ),
        "entitlement_minimization_transformer": ("entitlement_minimization_transformer", "Transformer"),
        "entitlement_recertification_packet_builder": (
            "entitlement_recertification_packet_builder",
            "Aggregator",
        ),
        # Supplier evidence fan-in services.
        "supplier_certificate_pdf_ingestor": ("supplier_certificate_pdf_ingestor", "Extractor"),
        "supplier_master_table_ingestor": ("supplier_master_table_ingestor", "Extractor"),
        "supplier_policy_json_ingestor": ("supplier_policy_json_ingestor", "Extractor"),
        "supplier_compliance_contract_validator": (
            "supplier_compliance_contract_validator",
            "QualityCheck",
        ),
        "supplier_evidence_normalizer": ("supplier_evidence_normalizer", "Transformer"),
        "supplier_policy_evidence_fuser": ("supplier_policy_evidence_fuser", "Integrator"),
        "supplier_sensitive_evidence_detector": ("supplier_sensitive_evidence_detector", "DomainAdapter"),
        "supplier_evidence_minimization_transformer": (
            "supplier_evidence_minimization_transformer",
            "Transformer",
        ),
        "supplier_compliance_review_packet_builder": (
            "supplier_compliance_review_packet_builder",
            "Aggregator",
        ),
        "supplier_compliance_bundle_publisher": ("supplier_compliance_bundle_publisher", "Publisher"),
        # Policy/privacy distractors.
        "redaction_only_text_filter": ("redaction_only_text_filter", "Transformer"),
        "generic_human_review_ticket_creator": (
            "generic_human_review_ticket_creator",
            "Publisher",
        ),
        "audit_log_append_only_writer": ("audit_log_append_only_writer", "Loader"),
        "privacy_policy_table_loader": ("privacy_policy_table_loader", "Extractor"),
        "case_status_notifier": ("case_status_notifier", "Publisher"),
    }
)

base.DISTRACTORS = [
    "redaction_only_text_filter",
    "generic_human_review_ticket_creator",
    "audit_log_append_only_writer",
    "privacy_policy_table_loader",
    "case_status_notifier",
    "reviewed_domain_adapter",
]


PIPELINE_SERVICE_MAP: dict[str, dict[str, tuple[str, str]]] = {
    "clinical_note_phi_review_packet": {
        "ingest_source_batch": ("clinical_note_batch_ingestor", "Extractor"),
        "validate_source_contract": ("clinical_phi_contract_validator", "QualityCheck"),
        "detect_sensitive_fields": ("clinical_phi_detector", "DomainAdapter"),
        "apply_redaction_or_suppression": ("clinical_note_redaction_transformer", "Transformer"),
        "create_human_review_packet": ("clinical_phi_review_packet_builder", "Aggregator"),
        "evaluate_policy_or_risk": ("clinical_phi_policy_risk_decider", "DomainAdapter"),
        "route_approved_records": ("clinical_phi_release_router", "Publisher"),
        "route_exception_records": ("clinical_phi_review_queue_router", "Publisher"),
        "merge_route_outcomes": ("policy_route_outcome_merger", "Aggregator"),
        "publish_outputs": ("policy_review_bundle_publisher", "Publisher"),
    },
    "financial_transaction_escalation_review": {
        "ingest_source_batch": ("transaction_policy_batch_ingestor", "Extractor"),
        "validate_source_contract": ("transaction_escalation_contract_validator", "QualityCheck"),
        "detect_sensitive_fields": ("transaction_sensitive_field_detector", "DomainAdapter"),
        "apply_redaction_or_suppression": ("transaction_minimization_transformer", "Transformer"),
        "create_human_review_packet": ("transaction_escalation_packet_builder", "Aggregator"),
        "evaluate_policy_or_risk": ("transaction_escalation_policy_decider", "DomainAdapter"),
        "route_approved_records": ("transaction_low_risk_status_router", "Publisher"),
        "route_exception_records": ("transaction_case_review_router", "Publisher"),
        "merge_route_outcomes": ("policy_route_outcome_merger", "Aggregator"),
        "publish_outputs": ("policy_review_bundle_publisher", "Publisher"),
    },
    "student_record_privacy_review": {
        "ingest_source_batch": ("student_record_privacy_batch_ingestor", "Extractor"),
        "validate_source_contract": ("student_privacy_contract_validator", "QualityCheck"),
        "evaluate_policy_or_risk": ("student_research_release_policy_decider", "DomainAdapter"),
        "route_approved_records": ("student_redacted_release_router", "Publisher"),
        "route_exception_records": ("student_steward_review_router", "Publisher"),
        "merge_route_outcomes": ("policy_route_outcome_merger", "Aggregator"),
        "publish_outputs": ("policy_review_bundle_publisher", "Publisher"),
    },
    "access_entitlement_recertification": {
        "ingest_primary_source": ("identity_provider_export_ingestor", "Extractor"),
        "ingest_secondary_source": ("resource_entitlement_table_ingestor", "Extractor"),
        "ingest_reference_source": ("manager_directory_reference_ingestor", "Extractor"),
        "validate_source_contracts": ("entitlement_recertification_contract_validator", "QualityCheck"),
        "normalize_sources": ("entitlement_identity_normalizer", "Transformer"),
        "fuse_sources": ("entitlement_identity_resource_fuser", "Integrator"),
        "detect_sensitive_fields": ("entitlement_sensitive_attribute_detector", "DomainAdapter"),
        "apply_redaction_or_suppression": ("entitlement_minimization_transformer", "Transformer"),
        "create_human_review_packet": ("entitlement_recertification_packet_builder", "Aggregator"),
        "record_policy_decision": ("policy_decision_audit_recorder", "Loader"),
        "write_audit_log": ("policy_audit_log_writer", "Loader"),
        "notify_reviewer_or_owner": ("reviewer_notification_publisher", "Publisher"),
        "publish_outputs": ("policy_review_bundle_publisher", "Publisher"),
    },
    "supplier_compliance_evidence_review": {
        "ingest_primary_source": ("supplier_certificate_pdf_ingestor", "Extractor"),
        "ingest_secondary_source": ("supplier_master_table_ingestor", "Extractor"),
        "ingest_reference_source": ("supplier_policy_json_ingestor", "Extractor"),
        "validate_source_contracts": ("supplier_compliance_contract_validator", "QualityCheck"),
        "normalize_sources": ("supplier_evidence_normalizer", "Transformer"),
        "fuse_sources": ("supplier_policy_evidence_fuser", "Integrator"),
        "detect_sensitive_fields": ("supplier_sensitive_evidence_detector", "DomainAdapter"),
        "apply_redaction_or_suppression": ("supplier_evidence_minimization_transformer", "Transformer"),
        "create_human_review_packet": ("supplier_compliance_review_packet_builder", "Aggregator"),
        "publish_outputs": ("supplier_compliance_bundle_publisher", "Publisher"),
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
    source_review = ROOT / "benchmark" / "catalog" / "review" / "0.3.5" / "candidate_relationships.private.json"
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
        raise FileNotFoundError("Batch 07 requires catalog snapshot 0.3.5 from Batch 06")
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
    print("authored extension batch 07: 5 instances and catalogue 0.3.6")


if __name__ == "__main__":
    main()
