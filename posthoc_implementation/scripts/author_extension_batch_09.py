#!/usr/bin/env python3
"""Author Extension-50 batch 09 AI/LLM/NLP benchmark instances."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import author_extension_batch_01 as base  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]

base.SOURCE_ROOT = ROOT / "benchmark" / "source" / "extension_v1" / "batch_09"
base.CATALOG_VERSION = "0.3.8"
base.CATALOG_SOURCE = ROOT / "benchmark" / "catalog" / "snapshots" / "0.3.7"
base.CATALOG_TARGET = ROOT / "benchmark" / "catalog" / "snapshots" / base.CATALOG_VERSION
base.DESCRIPTOR_CONTEXT = "deterministic AI, LLM, NLP, embedding, retrieval, and review workflows"
base.DESCRIPTOR_KEYWORDS = ["ai", "llm", "nlp", "embedding", "retrieval", "rag"]
base.DESCRIPTOR_SOURCE_REF = "extension-batch-09:ai-llm-nlp-curation"

base.TOPOLOGY_MAP.update(
    {
        "staged": "staged_etl",
        "branch_gate": "branch_merge",
        "fan_out_fan_in": "fan_out_fan_in",
    }
)

base.SERVICE_BY_STEP.update(
    {
        # Shared AI/RAG services.
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
        "ai_route_outcome_merger": ("ai_route_outcome_merger", "Aggregator"),
        "ai_completion_bundle_publisher": ("ai_completion_bundle_publisher", "Publisher"),
        # PDF policy corpus services.
        "policy_pdf_corpus_ingestor": ("policy_pdf_corpus_ingestor", "Extractor"),
        "policy_corpus_contract_validator": ("policy_corpus_contract_validator", "QualityCheck"),
        "policy_corpus_structured_extractor": (
            "policy_corpus_structured_extractor",
            "DomainAdapter",
        ),
        "policy_corpus_confidence_scorer": ("policy_corpus_confidence_scorer", "ScoringService"),
        "policy_corpus_review_packet_builder": (
            "policy_corpus_review_packet_builder",
            "Aggregator",
        ),
        "policy_vector_index_manifest_publisher": (
            "policy_vector_index_manifest_publisher",
            "Publisher",
        ),
        # Contract risk services.
        "contract_pdf_bundle_ingestor": ("contract_pdf_bundle_ingestor", "Extractor"),
        "contract_clause_contract_validator": ("contract_clause_contract_validator", "QualityCheck"),
        "contract_clause_structured_extractor": (
            "contract_clause_structured_extractor",
            "DomainAdapter",
        ),
        "contract_clause_risk_decider": ("contract_clause_risk_decider", "DomainAdapter"),
        "contract_clause_low_risk_router": ("contract_clause_low_risk_router", "Publisher"),
        "contract_clause_legal_review_router": (
            "contract_clause_legal_review_router",
            "Publisher",
        ),
        # Clinical note services.
        "clinical_note_ai_batch_ingestor": ("clinical_note_ai_batch_ingestor", "Extractor"),
        "clinical_note_deid_contract_validator": (
            "clinical_note_deid_contract_validator",
            "QualityCheck",
        ),
        "clinical_note_text_parser": ("clinical_note_text_parser", "Extractor"),
        "clinical_note_deid_summary_extractor": (
            "clinical_note_deid_summary_extractor",
            "DomainAdapter",
        ),
        "clinical_note_deid_policy_decider": (
            "clinical_note_deid_policy_decider",
            "DomainAdapter",
        ),
        "clinical_note_safe_summary_router": (
            "clinical_note_safe_summary_router",
            "Publisher",
        ),
        "clinical_note_phi_review_router": ("clinical_note_phi_review_router", "Publisher"),
        # Scientific literature services.
        "literature_pdf_bundle_ingestor": ("literature_pdf_bundle_ingestor", "Extractor"),
        "literature_screening_contract_validator": (
            "literature_screening_contract_validator",
            "QualityCheck",
        ),
        "article_pdf_partition_normalizer": ("article_pdf_partition_normalizer", "Transformer"),
        "screening_criteria_partition_normalizer": (
            "screening_criteria_partition_normalizer",
            "Transformer",
        ),
        "reviewer_roster_partition_normalizer": (
            "reviewer_roster_partition_normalizer",
            "Transformer",
        ),
        "literature_screening_context_fuser": (
            "literature_screening_context_fuser",
            "Integrator",
        ),
        "literature_screening_bundle_publisher": (
            "literature_screening_bundle_publisher",
            "Publisher",
        ),
        # Support semantic routing services.
        "support_ticket_text_batch_ingestor": (
            "support_ticket_text_batch_ingestor",
            "Extractor",
        ),
        "support_ticket_contract_validator": (
            "support_ticket_contract_validator",
            "QualityCheck",
        ),
        "support_ticket_text_parser": ("support_ticket_text_parser", "Extractor"),
        "support_ticket_intent_classifier": ("support_ticket_intent_classifier", "DomainAdapter"),
        "support_ticket_routing_policy_decider": (
            "support_ticket_routing_policy_decider",
            "DomainAdapter",
        ),
        "support_ticket_auto_route_publisher": (
            "support_ticket_auto_route_publisher",
            "Publisher",
        ),
        "support_ticket_manual_review_router": (
            "support_ticket_manual_review_router",
            "Publisher",
        ),
        # AI/RAG distractors.
        "keyword_only_document_searcher": ("keyword_only_document_searcher", "Extractor"),
        "embedding_index_manifest_archiver": ("embedding_index_manifest_archiver", "Loader"),
        "generic_llm_prompt_runner": ("generic_llm_prompt_runner", "DomainAdapter"),
        "chunk_count_quality_checker": ("chunk_count_quality_checker", "QualityCheck"),
        "uncontextualized_summary_generator": (
            "uncontextualized_summary_generator",
            "DomainAdapter",
        ),
    }
)

base.DISTRACTORS = [
    "keyword_only_document_searcher",
    "embedding_index_manifest_archiver",
    "generic_llm_prompt_runner",
    "chunk_count_quality_checker",
    "uncontextualized_summary_generator",
    "reviewed_domain_adapter",
]


PIPELINE_SERVICE_MAP: dict[str, dict[str, tuple[str, str]]] = {
    "pdf_policy_corpus_ingestion": {
        "ingest_source_batch": ("policy_pdf_corpus_ingestor", "Extractor"),
        "validate_source_contract": ("policy_corpus_contract_validator", "QualityCheck"),
        "stage_raw_artifacts": ("ai_raw_artifact_stager", "Loader"),
        "normalize_records": ("ai_record_metadata_normalizer", "Transformer"),
        "extract_or_parse_text": ("pdf_text_extraction_parser", "Extractor"),
        "chunk_documents": ("semantic_document_chunker", "Transformer"),
        "generate_embeddings": ("deterministic_text_embedding_generator", "Transformer"),
        "write_vector_index": ("fixture_vector_index_writer", "Loader"),
        "retrieve_grounding_context": ("grounding_context_retriever", "Extractor"),
        "run_structured_extraction": ("policy_corpus_structured_extractor", "DomainAdapter"),
        "score_confidence_and_policy": ("policy_corpus_confidence_scorer", "ScoringService"),
        "create_human_review_packet": ("policy_corpus_review_packet_builder", "Aggregator"),
        "publish_outputs": ("policy_vector_index_manifest_publisher", "Publisher"),
    },
    "contract_clause_risk_extraction": {
        "ingest_source_batch": ("contract_pdf_bundle_ingestor", "Extractor"),
        "validate_source_contract": ("contract_clause_contract_validator", "QualityCheck"),
        "extract_or_parse_text": ("pdf_text_extraction_parser", "Extractor"),
        "chunk_documents": ("semantic_document_chunker", "Transformer"),
        "generate_embeddings": ("deterministic_text_embedding_generator", "Transformer"),
        "write_vector_index": ("fixture_vector_index_writer", "Loader"),
        "retrieve_grounding_context": ("grounding_context_retriever", "Extractor"),
        "run_structured_extraction": ("contract_clause_structured_extractor", "DomainAdapter"),
        "evaluate_policy_or_risk": ("contract_clause_risk_decider", "DomainAdapter"),
        "route_approved_records": ("contract_clause_low_risk_router", "Publisher"),
        "route_exception_records": ("contract_clause_legal_review_router", "Publisher"),
        "merge_route_outcomes": ("ai_route_outcome_merger", "Aggregator"),
        "publish_outputs": ("ai_completion_bundle_publisher", "Publisher"),
    },
    "clinical_note_deidentification_summary": {
        "ingest_source_batch": ("clinical_note_ai_batch_ingestor", "Extractor"),
        "validate_source_contract": ("clinical_note_deid_contract_validator", "QualityCheck"),
        "extract_or_parse_text": ("clinical_note_text_parser", "Extractor"),
        "chunk_documents": ("semantic_document_chunker", "Transformer"),
        "generate_embeddings": ("deterministic_text_embedding_generator", "Transformer"),
        "write_vector_index": ("fixture_vector_index_writer", "Loader"),
        "retrieve_grounding_context": ("grounding_context_retriever", "Extractor"),
        "run_structured_extraction": ("clinical_note_deid_summary_extractor", "DomainAdapter"),
        "evaluate_policy_or_risk": ("clinical_note_deid_policy_decider", "DomainAdapter"),
        "route_approved_records": ("clinical_note_safe_summary_router", "Publisher"),
        "route_exception_records": ("clinical_note_phi_review_router", "Publisher"),
        "merge_route_outcomes": ("ai_route_outcome_merger", "Aggregator"),
        "publish_outputs": ("ai_completion_bundle_publisher", "Publisher"),
    },
    "scientific_literature_screening": {
        "ingest_source_batch": ("literature_pdf_bundle_ingestor", "Extractor"),
        "validate_source_contract": ("literature_screening_contract_validator", "QualityCheck"),
        "normalize_partition_a": ("article_pdf_partition_normalizer", "Transformer"),
        "normalize_partition_b": ("screening_criteria_partition_normalizer", "Transformer"),
        "normalize_partition_c": ("reviewer_roster_partition_normalizer", "Transformer"),
        "fuse_partitions": ("literature_screening_context_fuser", "Integrator"),
        "extract_or_parse_text": ("pdf_text_extraction_parser", "Extractor"),
        "chunk_documents": ("semantic_document_chunker", "Transformer"),
        "generate_embeddings": ("deterministic_text_embedding_generator", "Transformer"),
        "publish_outputs": ("literature_screening_bundle_publisher", "Publisher"),
    },
    "support_ticket_semantic_routing": {
        "ingest_source_batch": ("support_ticket_text_batch_ingestor", "Extractor"),
        "validate_source_contract": ("support_ticket_contract_validator", "QualityCheck"),
        "extract_or_parse_text": ("support_ticket_text_parser", "Extractor"),
        "chunk_documents": ("semantic_document_chunker", "Transformer"),
        "generate_embeddings": ("deterministic_text_embedding_generator", "Transformer"),
        "write_vector_index": ("fixture_vector_index_writer", "Loader"),
        "retrieve_grounding_context": ("grounding_context_retriever", "Extractor"),
        "run_structured_extraction": ("support_ticket_intent_classifier", "DomainAdapter"),
        "evaluate_policy_or_risk": ("support_ticket_routing_policy_decider", "DomainAdapter"),
        "route_approved_records": ("support_ticket_auto_route_publisher", "Publisher"),
        "route_exception_records": ("support_ticket_manual_review_router", "Publisher"),
        "merge_route_outcomes": ("ai_route_outcome_merger", "Aggregator"),
        "publish_outputs": ("ai_completion_bundle_publisher", "Publisher"),
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
    source_review = ROOT / "benchmark" / "catalog" / "review" / "0.3.7" / "candidate_relationships.private.json"
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
        raise FileNotFoundError("Batch 09 requires catalog snapshot 0.3.7 from Batch 08")
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
    print("authored extension batch 09: 5 instances and catalogue 0.3.8")


if __name__ == "__main__":
    main()
