#!/usr/bin/env python3
"""Author Extension-50 batch 10 AI/LLM/NLP benchmark instances."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import author_extension_batch_01 as base  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]

base.SOURCE_ROOT = ROOT / "benchmark" / "source" / "extension_v1" / "batch_10"
base.CATALOG_VERSION = "0.3.9"
base.CATALOG_SOURCE = ROOT / "benchmark" / "catalog" / "snapshots" / "0.3.8"
base.CATALOG_TARGET = ROOT / "benchmark" / "catalog" / "snapshots" / base.CATALOG_VERSION
base.DESCRIPTOR_CONTEXT = "deterministic multimodal AI, RAG, extraction, reconciliation, and summarization workflows"
base.DESCRIPTOR_KEYWORDS = ["ai", "llm", "nlp", "multimodal", "rag", "extraction"]
base.DESCRIPTOR_SOURCE_REF = "extension-batch-10:ai-llm-nlp-curation"

base.TOPOLOGY_MAP.update(
    {
        "staged": "staged_etl",
        "fan_in": "fan_out_fan_in",
        "fan_out_fan_in": "fan_out_fan_in",
    }
)

base.SERVICE_BY_STEP.update(
    {
        # Reused AI/RAG primitives from Batch 09.
        "ai_raw_artifact_stager": ("ai_raw_artifact_stager", "Loader"),
        "ai_record_metadata_normalizer": ("ai_record_metadata_normalizer", "Transformer"),
        "pdf_text_extraction_parser": ("pdf_text_extraction_parser", "Extractor"),
        "semantic_document_chunker": ("semantic_document_chunker", "Transformer"),
        "deterministic_text_embedding_generator": (
            "deterministic_text_embedding_generator",
            "Transformer",
        ),
        "fixture_vector_index_writer": ("fixture_vector_index_writer", "Loader"),
        "grounding_context_retriever": ("grounding_context_retriever", "Extractor"),
        "policy_corpus_confidence_scorer": ("policy_corpus_confidence_scorer", "ScoringService"),
        "policy_corpus_review_packet_builder": (
            "policy_corpus_review_packet_builder",
            "Aggregator",
        ),
        # Product listing services.
        "product_multimodal_batch_ingestor": ("product_multimodal_batch_ingestor", "Extractor"),
        "product_listing_contract_validator": ("product_listing_contract_validator", "QualityCheck"),
        "product_image_partition_normalizer": ("product_image_partition_normalizer", "Transformer"),
        "product_text_partition_normalizer": ("product_text_partition_normalizer", "Transformer"),
        "product_taxonomy_partition_normalizer": (
            "product_taxonomy_partition_normalizer",
            "Transformer",
        ),
        "product_listing_context_fuser": ("product_listing_context_fuser", "Integrator"),
        "product_listing_summary_parser": ("product_listing_summary_parser", "Extractor"),
        "product_listing_enrichment_publisher": (
            "product_listing_enrichment_publisher",
            "Publisher",
        ),
        # Invoice reconciliation services.
        "invoice_pdf_bundle_ingestor": ("invoice_pdf_bundle_ingestor", "Extractor"),
        "purchase_order_table_ingestor": ("purchase_order_table_ingestor", "Extractor"),
        "vendor_registry_json_ingestor": ("vendor_registry_json_ingestor", "Extractor"),
        "invoice_reconciliation_contract_validator": (
            "invoice_reconciliation_contract_validator",
            "QualityCheck",
        ),
        "invoice_reference_record_normalizer": (
            "invoice_reference_record_normalizer",
            "Transformer",
        ),
        "invoice_purchase_order_context_fuser": (
            "invoice_purchase_order_context_fuser",
            "Integrator",
        ),
        "invoice_field_extraction_parser": ("invoice_field_extraction_parser", "Extractor"),
        "invoice_reconciliation_bundle_publisher": (
            "invoice_reconciliation_bundle_publisher",
            "Publisher",
        ),
        # RAG answer-pack services.
        "rag_source_bundle_ingestor": ("rag_source_bundle_ingestor", "Extractor"),
        "rag_answer_pack_contract_validator": (
            "rag_answer_pack_contract_validator",
            "QualityCheck",
        ),
        "rag_document_partition_normalizer": ("rag_document_partition_normalizer", "Transformer"),
        "rag_question_partition_normalizer": ("rag_question_partition_normalizer", "Transformer"),
        "rag_config_partition_normalizer": ("rag_config_partition_normalizer", "Transformer"),
        "rag_corpus_question_config_fuser": ("rag_corpus_question_config_fuser", "Integrator"),
        "rag_grounded_answer_generator": ("rag_grounded_answer_generator", "DomainAdapter"),
        "rag_answer_pack_publisher": ("rag_answer_pack_publisher", "Publisher"),
        # Compliance evidence services.
        "compliance_evidence_bundle_ingestor": (
            "compliance_evidence_bundle_ingestor",
            "Extractor",
        ),
        "control_framework_json_ingestor": ("control_framework_json_ingestor", "Extractor"),
        "audit_request_table_ingestor": ("audit_request_table_ingestor", "Extractor"),
        "compliance_evidence_contract_validator": (
            "compliance_evidence_contract_validator",
            "QualityCheck",
        ),
        "compliance_evidence_normalizer": ("compliance_evidence_normalizer", "Transformer"),
        "compliance_control_context_fuser": ("compliance_control_context_fuser", "Integrator"),
        "compliance_control_mapping_summarizer": (
            "compliance_control_mapping_summarizer",
            "DomainAdapter",
        ),
        "compliance_summary_bundle_publisher": (
            "compliance_summary_bundle_publisher",
            "Publisher",
        ),
        # Meeting transcript services.
        "meeting_transcript_batch_ingestor": ("meeting_transcript_batch_ingestor", "Extractor"),
        "meeting_transcript_contract_validator": (
            "meeting_transcript_contract_validator",
            "QualityCheck",
        ),
        "meeting_transcript_text_parser": ("meeting_transcript_text_parser", "Extractor"),
        "meeting_decision_action_extractor": (
            "meeting_decision_action_extractor",
            "DomainAdapter",
        ),
        "meeting_action_confidence_scorer": ("meeting_action_confidence_scorer", "ScoringService"),
        "meeting_action_review_packet_builder": (
            "meeting_action_review_packet_builder",
            "Aggregator",
        ),
        "meeting_action_register_publisher": (
            "meeting_action_register_publisher",
            "Publisher",
        ),
        # Final-batch distractors.
        "image_caption_only_generator": ("image_caption_only_generator", "DomainAdapter"),
        "invoice_ocr_without_reconciliation": (
            "invoice_ocr_without_reconciliation",
            "Extractor",
        ),
        "rag_index_without_answer_generator": ("rag_index_without_answer_generator", "Loader"),
        "generic_control_mapping_table_joiner": (
            "generic_control_mapping_table_joiner",
            "Integrator",
        ),
        "meeting_summary_without_action_owner": (
            "meeting_summary_without_action_owner",
            "DomainAdapter",
        ),
    }
)

base.DISTRACTORS = [
    "image_caption_only_generator",
    "invoice_ocr_without_reconciliation",
    "rag_index_without_answer_generator",
    "generic_control_mapping_table_joiner",
    "meeting_summary_without_action_owner",
    "reviewed_domain_adapter",
]


PIPELINE_SERVICE_MAP: dict[str, dict[str, tuple[str, str]]] = {
    "multimodal_product_listing_ai_enrichment": {
        "ingest_source_batch": ("product_multimodal_batch_ingestor", "Extractor"),
        "validate_source_contract": ("product_listing_contract_validator", "QualityCheck"),
        "normalize_partition_a": ("product_image_partition_normalizer", "Transformer"),
        "normalize_partition_b": ("product_text_partition_normalizer", "Transformer"),
        "normalize_partition_c": ("product_taxonomy_partition_normalizer", "Transformer"),
        "fuse_partitions": ("product_listing_context_fuser", "Integrator"),
        "extract_or_parse_text": ("product_listing_summary_parser", "Extractor"),
        "chunk_documents": ("semantic_document_chunker", "Transformer"),
        "generate_embeddings": ("deterministic_text_embedding_generator", "Transformer"),
        "publish_outputs": ("product_listing_enrichment_publisher", "Publisher"),
    },
    "invoice_pdf_extraction_reconciliation": {
        "ingest_primary_source": ("invoice_pdf_bundle_ingestor", "Extractor"),
        "ingest_secondary_source": ("purchase_order_table_ingestor", "Extractor"),
        "ingest_reference_source": ("vendor_registry_json_ingestor", "Extractor"),
        "validate_source_contracts": ("invoice_reconciliation_contract_validator", "QualityCheck"),
        "normalize_sources": ("invoice_reference_record_normalizer", "Transformer"),
        "fuse_sources": ("invoice_purchase_order_context_fuser", "Integrator"),
        "extract_or_parse_text": ("invoice_field_extraction_parser", "Extractor"),
        "chunk_documents": ("semantic_document_chunker", "Transformer"),
        "generate_embeddings": ("deterministic_text_embedding_generator", "Transformer"),
        "publish_outputs": ("invoice_reconciliation_bundle_publisher", "Publisher"),
    },
    "rag_answer_pack_builder": {
        "ingest_source_batch": ("rag_source_bundle_ingestor", "Extractor"),
        "validate_source_contract": ("rag_answer_pack_contract_validator", "QualityCheck"),
        "normalize_partition_a": ("rag_document_partition_normalizer", "Transformer"),
        "normalize_partition_b": ("rag_question_partition_normalizer", "Transformer"),
        "normalize_partition_c": ("rag_config_partition_normalizer", "Transformer"),
        "fuse_partitions": ("rag_corpus_question_config_fuser", "Integrator"),
        "extract_or_parse_text": ("pdf_text_extraction_parser", "Extractor"),
        "chunk_documents": ("semantic_document_chunker", "Transformer"),
        "generate_embeddings": ("deterministic_text_embedding_generator", "Transformer"),
        "write_vector_index": ("fixture_vector_index_writer", "Loader"),
        "retrieve_grounding_context": ("grounding_context_retriever", "Extractor"),
        "run_structured_extraction": ("rag_grounded_answer_generator", "DomainAdapter"),
        "publish_outputs": ("rag_answer_pack_publisher", "Publisher"),
    },
    "compliance_evidence_summarizer": {
        "ingest_primary_source": ("compliance_evidence_bundle_ingestor", "Extractor"),
        "ingest_secondary_source": ("control_framework_json_ingestor", "Extractor"),
        "ingest_reference_source": ("audit_request_table_ingestor", "Extractor"),
        "validate_source_contracts": ("compliance_evidence_contract_validator", "QualityCheck"),
        "normalize_sources": ("compliance_evidence_normalizer", "Transformer"),
        "fuse_sources": ("compliance_control_context_fuser", "Integrator"),
        "extract_or_parse_text": ("pdf_text_extraction_parser", "Extractor"),
        "chunk_documents": ("semantic_document_chunker", "Transformer"),
        "generate_embeddings": ("deterministic_text_embedding_generator", "Transformer"),
        "write_vector_index": ("fixture_vector_index_writer", "Loader"),
        "retrieve_grounding_context": ("grounding_context_retriever", "Extractor"),
        "run_structured_extraction": ("compliance_control_mapping_summarizer", "DomainAdapter"),
        "publish_outputs": ("compliance_summary_bundle_publisher", "Publisher"),
    },
    "meeting_transcript_action_extraction": {
        "ingest_source_batch": ("meeting_transcript_batch_ingestor", "Extractor"),
        "validate_source_contract": ("meeting_transcript_contract_validator", "QualityCheck"),
        "stage_raw_artifacts": ("ai_raw_artifact_stager", "Loader"),
        "normalize_records": ("ai_record_metadata_normalizer", "Transformer"),
        "extract_or_parse_text": ("meeting_transcript_text_parser", "Extractor"),
        "chunk_documents": ("semantic_document_chunker", "Transformer"),
        "generate_embeddings": ("deterministic_text_embedding_generator", "Transformer"),
        "write_vector_index": ("fixture_vector_index_writer", "Loader"),
        "retrieve_grounding_context": ("grounding_context_retriever", "Extractor"),
        "run_structured_extraction": ("meeting_decision_action_extractor", "DomainAdapter"),
        "score_confidence_and_policy": ("meeting_action_confidence_scorer", "ScoringService"),
        "create_human_review_packet": ("meeting_action_review_packet_builder", "Aggregator"),
        "publish_outputs": ("meeting_action_register_publisher", "Publisher"),
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
    source_review = ROOT / "benchmark" / "catalog" / "review" / "0.3.8" / "candidate_relationships.private.json"
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
        raise FileNotFoundError("Batch 10 requires catalog snapshot 0.3.8 from Batch 09")
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
    print("authored extension batch 10: 5 instances and catalogue 0.3.9")


if __name__ == "__main__":
    main()
