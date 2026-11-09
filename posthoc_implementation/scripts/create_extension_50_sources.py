#!/usr/bin/env python3
"""Create the synthetic, provenance-marked Extension-50 source corpus.

The generated package is intentionally source-only. It contains public pipeline
descriptions and companion source specifications, but no ServiceFlowIR, bindings,
candidate labels, or hidden gold annotations.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "benchmark" / "source" / "extension_v1"

TARGET_STEP_COUNTS = {
    "simple": 5,
    "medium": 7,
    "complex": 10,
    "very_complex": 13,
}


BLUEPRINTS: list[dict[str, Any]] = [
    # Diversity-40: image/document multimodal pipelines (10)
    {
        "pipeline_id": "medical_image_metadata_quality_check",
        "name": "Medical Image Metadata Quality Check",
        "track": "image_document_multimodal",
        "domain": "Healthcare/Public Health",
        "topology": "linear",
        "complexity": "simple",
        "subject": "medical image study metadata",
        "input_modalities": ["image", "json", "table"],
        "output_modalities": ["json", "table", "status"],
        "primary_inputs": ["DICOM image folder", "study manifest JSON", "patient scheduling CSV"],
        "external_systems": ["imaging object store", "metadata registry"],
        "scenario": "Prepare fixture-backed radiology image metadata for downstream quality monitoring without contacting a production PACS.",
    },
    {
        "pipeline_id": "satellite_change_report_assembler",
        "name": "Satellite Change Report Assembler",
        "track": "image_document_multimodal",
        "domain": "Environmental/Energy",
        "topology": "staged",
        "complexity": "medium",
        "subject": "satellite image change evidence",
        "input_modalities": ["image", "geojson", "table"],
        "output_modalities": ["pdf", "geojson", "table"],
        "primary_inputs": ["before imagery tiles", "after imagery tiles", "region boundary GeoJSON", "inspection registry CSV"],
        "external_systems": ["geospatial object store", "inspection report archive"],
        "scenario": "Build a bounded batch change report from paired satellite images and region metadata.",
    },
    {
        "pipeline_id": "scanned_claim_packet_extraction",
        "name": "Scanned Claim Packet Extraction",
        "track": "image_document_multimodal",
        "domain": "Finance/Risk",
        "topology": "fan_out",
        "complexity": "complex",
        "subject": "scanned insurance claim packet",
        "input_modalities": ["pdf", "image", "table"],
        "output_modalities": ["json", "table", "review_packet"],
        "primary_inputs": ["scanned claim PDF", "claim image attachments", "policyholder CSV"],
        "external_systems": ["claims document bucket", "review queue"],
        "scenario": "Extract structured fields and review evidence from scanned claim packets.",
    },
    {
        "pipeline_id": "product_image_listing_enrichment",
        "name": "Product Image Listing Enrichment",
        "track": "image_document_multimodal",
        "domain": "Retail/E-commerce",
        "topology": "fan_out",
        "complexity": "medium",
        "subject": "product image and listing metadata",
        "input_modalities": ["image", "json", "table"],
        "output_modalities": ["json", "table"],
        "primary_inputs": ["product image folder", "listing JSON export", "category taxonomy CSV"],
        "external_systems": ["catalog object store", "marketplace staging API"],
        "scenario": "Enrich product listings with image-derived quality and attribute signals.",
    },
    {
        "pipeline_id": "identity_document_redaction",
        "name": "Identity Document Redaction",
        "track": "image_document_multimodal",
        "domain": "Legal/Compliance",
        "topology": "branch_gate",
        "complexity": "complex",
        "subject": "identity document evidence",
        "input_modalities": ["image", "pdf", "json"],
        "output_modalities": ["redacted_pdf", "json", "audit_log"],
        "primary_inputs": ["identity document scan", "case metadata JSON", "redaction policy JSON"],
        "external_systems": ["secure evidence bucket", "manual review queue"],
        "scenario": "Detect sensitive fields in identity evidence, redact approved copies, and route uncertain cases.",
    },
    {
        "pipeline_id": "handwritten_form_digitization",
        "name": "Handwritten Form Digitization",
        "track": "image_document_multimodal",
        "domain": "Public Sector/Geospatial",
        "topology": "staged",
        "complexity": "medium",
        "subject": "handwritten public-service form",
        "input_modalities": ["image", "pdf", "table"],
        "output_modalities": ["json", "table", "review_packet"],
        "primary_inputs": ["form scan images", "form template PDF", "office routing CSV"],
        "external_systems": ["forms intake bucket", "casework staging table"],
        "scenario": "Convert handwritten intake forms into structured case records with confidence checks.",
    },
    {
        "pipeline_id": "shipping_document_ocr_reconciliation",
        "name": "Shipping Document OCR Reconciliation",
        "track": "image_document_multimodal",
        "domain": "Supply Chain/Manufacturing",
        "topology": "fan_in",
        "complexity": "complex",
        "subject": "shipping document OCR evidence",
        "input_modalities": ["pdf", "image", "table", "json"],
        "output_modalities": ["table", "json", "exception_report"],
        "primary_inputs": ["bill of lading PDF", "container photo set", "shipment manifest CSV", "carrier API snapshot"],
        "external_systems": ["logistics document store", "exception management queue"],
        "scenario": "Reconcile OCR-derived shipping details with manifests and carrier snapshots.",
    },
    {
        "pipeline_id": "floor_plan_asset_extraction",
        "name": "Floor Plan Asset Extraction",
        "track": "image_document_multimodal",
        "domain": "Public Sector/Geospatial",
        "topology": "fan_out_fan_in",
        "complexity": "complex",
        "subject": "building floor-plan asset inventory",
        "input_modalities": ["pdf", "image", "geojson"],
        "output_modalities": ["json", "geojson", "table"],
        "primary_inputs": ["floor-plan PDF", "room annotation image", "building boundary GeoJSON"],
        "external_systems": ["facilities drawing archive", "asset registry"],
        "scenario": "Extract room and asset evidence from floor-plan documents for a facilities registry.",
    },
    {
        "pipeline_id": "crop_disease_image_triage",
        "name": "Crop Disease Image Triage",
        "track": "image_document_multimodal",
        "domain": "Environmental/Energy",
        "topology": "branch_gate",
        "complexity": "simple",
        "subject": "crop disease image triage",
        "input_modalities": ["image", "json", "table"],
        "output_modalities": ["json", "status"],
        "primary_inputs": ["field image upload", "farm metadata JSON", "crop registry CSV"],
        "external_systems": ["agronomy intake bucket", "extension officer notification endpoint"],
        "scenario": "Prepare crop image evidence and route likely disease cases for expert review.",
    },
    {
        "pipeline_id": "document_image_compliance_packet",
        "name": "Document Image Compliance Packet",
        "track": "image_document_multimodal",
        "domain": "Legal/Compliance",
        "topology": "fan_out_fan_in",
        "complexity": "medium",
        "subject": "document image compliance packet",
        "input_modalities": ["pdf", "image", "text"],
        "output_modalities": ["review_packet", "audit_log", "json"],
        "primary_inputs": ["signed document PDF", "supporting image evidence", "policy checklist markdown"],
        "external_systems": ["compliance evidence store", "auditor review queue"],
        "scenario": "Assemble a compliance review packet from document images and policy checklist evidence.",
    },
    # Diversity-40: API/JSON + table fusion pipelines (6)
    {
        "pipeline_id": "crm_sales_enrichment_fusion",
        "name": "CRM Sales Enrichment Fusion",
        "track": "api_json_table_fusion",
        "domain": "Marketing/Customer Operations",
        "topology": "fan_in",
        "complexity": "medium",
        "subject": "CRM and sales enrichment records",
        "input_modalities": ["json", "table"],
        "output_modalities": ["table", "json"],
        "primary_inputs": ["CRM account API snapshot", "daily sales CSV", "territory lookup table"],
        "external_systems": ["CRM API fixture", "sales warehouse staging area"],
        "scenario": "Join CRM account attributes with tabular sales measures for campaign planning.",
    },
    {
        "pipeline_id": "payment_ledger_reconciliation",
        "name": "Payment Ledger Reconciliation",
        "track": "api_json_table_fusion",
        "domain": "Finance/Risk",
        "topology": "branch_gate",
        "complexity": "complex",
        "subject": "payment API and ledger reconciliation",
        "input_modalities": ["json", "table"],
        "output_modalities": ["table", "exception_report", "audit_log"],
        "primary_inputs": ["payment provider JSON export", "general ledger CSV", "merchant registry table"],
        "external_systems": ["payment API fixture", "finance exception queue"],
        "scenario": "Reconcile payment provider events against ledger postings and branch unresolved mismatches.",
    },
    {
        "pipeline_id": "weather_sales_feature_builder",
        "name": "Weather Sales Feature Builder",
        "track": "api_json_table_fusion",
        "domain": "Retail/E-commerce",
        "topology": "staged",
        "complexity": "simple",
        "subject": "weather and store-sales features",
        "input_modalities": ["json", "table"],
        "output_modalities": ["table", "feature_manifest"],
        "primary_inputs": ["weather API JSON snapshot", "store sales CSV", "store location table"],
        "external_systems": ["weather API fixture", "feature staging bucket"],
        "scenario": "Build weather-aware sales features from bounded API and table inputs.",
    },
    {
        "pipeline_id": "ehr_operations_fusion",
        "name": "EHR Operations Fusion",
        "track": "api_json_table_fusion",
        "domain": "Healthcare/Public Health",
        "topology": "fan_in",
        "complexity": "complex",
        "subject": "EHR API and operations dashboard records",
        "input_modalities": ["json", "table"],
        "output_modalities": ["table", "json", "status"],
        "primary_inputs": ["EHR encounter JSON export", "bed operations CSV", "department lookup table"],
        "external_systems": ["EHR API fixture", "operations warehouse"],
        "scenario": "Fuse encounter payloads with operational tables to prepare a de-identified command-center dataset.",
    },
    {
        "pipeline_id": "supplier_risk_api_table_fusion",
        "name": "Supplier Risk API Table Fusion",
        "track": "api_json_table_fusion",
        "domain": "Supply Chain/Manufacturing",
        "topology": "fan_in",
        "complexity": "medium",
        "subject": "supplier risk API and procurement table",
        "input_modalities": ["json", "table"],
        "output_modalities": ["table", "risk_report"],
        "primary_inputs": ["supplier risk API JSON", "purchase order CSV", "supplier master table"],
        "external_systems": ["risk intelligence API fixture", "procurement staging bucket"],
        "scenario": "Combine supplier risk indicators with procurement volume for exception prioritization.",
    },
    {
        "pipeline_id": "support_profile_context_join",
        "name": "Support Profile Context Join",
        "track": "api_json_table_fusion",
        "domain": "Marketing/Customer Operations",
        "topology": "fan_in",
        "complexity": "medium",
        "subject": "support ticket and customer profile context",
        "input_modalities": ["json", "table", "text"],
        "output_modalities": ["table", "json"],
        "primary_inputs": ["support ticket API export", "customer profile CSV", "subscription plan lookup"],
        "external_systems": ["support API fixture", "customer analytics bucket"],
        "scenario": "Join nested support-ticket payloads with customer profile tables for routing context.",
    },
    # Diversity-40: time-series/sensor/window pipelines (6)
    {
        "pipeline_id": "building_energy_window_aggregation",
        "name": "Building Energy Window Aggregation",
        "track": "time_series_sensor_window",
        "domain": "Environmental/Energy",
        "topology": "windowed_batch",
        "complexity": "simple",
        "subject": "building energy meter windows",
        "input_modalities": ["time_series", "table"],
        "output_modalities": ["table", "feature_manifest"],
        "primary_inputs": ["meter reading CSV", "building metadata table"],
        "external_systems": ["meter data bucket", "energy analytics staging area"],
        "scenario": "Aggregate bounded building energy readings into hourly and daily windows.",
    },
    {
        "pipeline_id": "environmental_sensor_anomaly_batch",
        "name": "Environmental Sensor Anomaly Batch",
        "track": "time_series_sensor_window",
        "domain": "Environmental/Energy",
        "topology": "windowed_batch",
        "complexity": "medium",
        "subject": "environmental sensor anomaly windows",
        "input_modalities": ["time_series", "json", "table"],
        "output_modalities": ["table", "alert_digest"],
        "primary_inputs": ["sensor telemetry JSONL", "station metadata CSV", "threshold policy JSON"],
        "external_systems": ["sensor data lake", "alert digest bucket"],
        "scenario": "Detect anomalies from finite environmental sensor windows with station-aware thresholds.",
    },
    {
        "pipeline_id": "manufacturing_telemetry_quality_scoring",
        "name": "Manufacturing Telemetry Quality Scoring",
        "track": "time_series_sensor_window",
        "domain": "Supply Chain/Manufacturing",
        "topology": "fan_out",
        "complexity": "medium",
        "subject": "manufacturing telemetry quality windows",
        "input_modalities": ["time_series", "table"],
        "output_modalities": ["table", "quality_report"],
        "primary_inputs": ["machine telemetry CSV", "production batch table", "quality threshold table"],
        "external_systems": ["factory telemetry bucket", "quality dashboard staging"],
        "scenario": "Score finite machine telemetry windows for missingness, drift, and production-batch consistency.",
    },
    {
        "pipeline_id": "hospital_occupancy_window_forecast_prep",
        "name": "Hospital Occupancy Window Forecast Prep",
        "track": "time_series_sensor_window",
        "domain": "Healthcare/Public Health",
        "topology": "fan_in",
        "complexity": "complex",
        "subject": "hospital occupancy forecast windows",
        "input_modalities": ["time_series", "json", "table"],
        "output_modalities": ["table", "feature_manifest"],
        "primary_inputs": ["bed occupancy time series", "admissions JSON snapshot", "department lookup table"],
        "external_systems": ["hospital operations bucket", "forecast feature store"],
        "scenario": "Prepare aligned occupancy windows and operational context for forecast evaluation.",
    },
    {
        "pipeline_id": "observability_metrics_incident_digest",
        "name": "Observability Metrics Incident Digest",
        "track": "time_series_sensor_window",
        "domain": "AI Platform Operations",
        "topology": "windowed_batch",
        "complexity": "medium",
        "subject": "observability metric incident windows",
        "input_modalities": ["time_series", "json", "text"],
        "output_modalities": ["alert_digest", "json", "table"],
        "primary_inputs": ["metrics JSONL export", "incident ticket CSV", "service catalog JSON"],
        "external_systems": ["observability export bucket", "incident digest store"],
        "scenario": "Summarize finite observability windows and attach incident context for operators.",
    },
    {
        "pipeline_id": "climate_station_gap_fill_alignment",
        "name": "Climate Station Gap Fill Alignment",
        "track": "time_series_sensor_window",
        "domain": "Environmental/Energy",
        "topology": "fan_in",
        "complexity": "simple",
        "subject": "climate station aligned observations",
        "input_modalities": ["time_series", "table"],
        "output_modalities": ["table", "quality_report"],
        "primary_inputs": ["station readings CSV", "station metadata CSV", "calendar table"],
        "external_systems": ["climate data bucket", "prepared observation archive"],
        "scenario": "Align climate station readings to a calendar grid and flag small gaps for imputation.",
    },
    # Diversity-40: event/checkpoint/windowed batch workflows (8)
    {
        "pipeline_id": "clickstream_session_window_batch",
        "name": "Clickstream Session Window Batch",
        "track": "event_checkpoint_windowed_batch",
        "domain": "Retail/E-commerce",
        "topology": "windowed_batch",
        "complexity": "simple",
        "subject": "clickstream session windows",
        "input_modalities": ["jsonl", "table"],
        "output_modalities": ["table", "checkpoint_manifest"],
        "primary_inputs": ["bounded clickstream JSONL", "user consent table", "previous checkpoint manifest"],
        "external_systems": ["event export bucket", "analytics staging bucket"],
        "scenario": "Sessionize a finite clickstream export and produce a checkpointed batch output.",
    },
    {
        "pipeline_id": "fraud_event_replay_checkpoint",
        "name": "Fraud Event Replay Checkpoint",
        "track": "event_checkpoint_windowed_batch",
        "domain": "Finance/Risk",
        "topology": "branch_gate",
        "complexity": "complex",
        "subject": "fraud event replay checkpoint",
        "input_modalities": ["jsonl", "table"],
        "output_modalities": ["exception_report", "checkpoint_manifest", "audit_log"],
        "primary_inputs": ["bounded transaction event log", "merchant table", "prior replay checkpoint"],
        "external_systems": ["fraud event archive", "investigation queue"],
        "scenario": "Replay a finite fraud-event batch from checkpoint and route high-risk exceptions.",
    },
    {
        "pipeline_id": "log_window_alert_digest",
        "name": "Log Window Alert Digest",
        "track": "event_checkpoint_windowed_batch",
        "domain": "AI Platform Operations",
        "topology": "windowed_batch",
        "complexity": "medium",
        "subject": "application log alert windows",
        "input_modalities": ["text", "jsonl"],
        "output_modalities": ["alert_digest", "json"],
        "primary_inputs": ["bounded application log export", "service ownership JSON", "alert rule table"],
        "external_systems": ["log archive bucket", "alert digest store"],
        "scenario": "Create a digest of alert-worthy events from finite log windows.",
    },
    {
        "pipeline_id": "iot_device_snapshot_transition",
        "name": "IoT Device Snapshot Transition",
        "track": "event_checkpoint_windowed_batch",
        "domain": "Environmental/Energy",
        "topology": "fan_in",
        "complexity": "medium",
        "subject": "IoT device snapshot transitions",
        "input_modalities": ["jsonl", "table"],
        "output_modalities": ["table", "checkpoint_manifest"],
        "primary_inputs": ["device event JSONL", "device registry CSV", "previous snapshot table"],
        "external_systems": ["IoT export bucket", "device state archive"],
        "scenario": "Apply a finite device-event batch to a previous snapshot and publish the new state.",
    },
    {
        "pipeline_id": "payment_settlement_checkpoint_reconcile",
        "name": "Payment Settlement Checkpoint Reconcile",
        "track": "event_checkpoint_windowed_batch",
        "domain": "Finance/Risk",
        "topology": "fan_in",
        "complexity": "medium",
        "subject": "payment settlement checkpoint reconciliation",
        "input_modalities": ["jsonl", "table"],
        "output_modalities": ["table", "exception_report", "checkpoint_manifest"],
        "primary_inputs": ["settlement event batch", "bank statement CSV", "previous settlement checkpoint"],
        "external_systems": ["settlement archive", "finance review queue"],
        "scenario": "Reconcile a bounded settlement-event batch against bank statements and update the checkpoint.",
    },
    {
        "pipeline_id": "notification_delivery_checkpoint_audit",
        "name": "Notification Delivery Checkpoint Audit",
        "track": "event_checkpoint_windowed_batch",
        "domain": "Marketing/Customer Operations",
        "topology": "windowed_batch",
        "complexity": "simple",
        "subject": "notification delivery checkpoint audit",
        "input_modalities": ["jsonl", "table"],
        "output_modalities": ["audit_log", "table", "checkpoint_manifest"],
        "primary_inputs": ["notification delivery events", "campaign audience CSV", "prior delivery checkpoint"],
        "external_systems": ["messaging export bucket", "campaign audit store"],
        "scenario": "Audit finite notification delivery events against an audience table and checkpoint progress.",
    },
    {
        "pipeline_id": "queue_backlog_snapshot_analysis",
        "name": "Queue Backlog Snapshot Analysis",
        "track": "event_checkpoint_windowed_batch",
        "domain": "AI Platform Operations",
        "topology": "windowed_batch",
        "complexity": "simple",
        "subject": "queue backlog snapshot analysis",
        "input_modalities": ["json", "table"],
        "output_modalities": ["table", "alert_digest"],
        "primary_inputs": ["queue snapshot JSON", "worker capacity table", "service priority table"],
        "external_systems": ["queue telemetry archive", "operations dashboard staging"],
        "scenario": "Analyze a finite queue backlog snapshot and identify priority capacity risks.",
    },
    {
        "pipeline_id": "late_record_replay_quarantine",
        "name": "Late Record Replay Quarantine",
        "track": "event_checkpoint_windowed_batch",
        "domain": "Legal/Compliance",
        "topology": "branch_gate",
        "complexity": "complex",
        "subject": "late record replay quarantine",
        "input_modalities": ["jsonl", "table"],
        "output_modalities": ["quarantine_report", "checkpoint_manifest", "audit_log"],
        "primary_inputs": ["late-arriving record batch", "retention policy table", "prior processing checkpoint"],
        "external_systems": ["records archive", "compliance review queue"],
        "scenario": "Replay late-arriving records against a checkpoint and quarantine policy-sensitive records.",
    },
    # Diversity-40: policy/privacy/human-review workflows (5)
    {
        "pipeline_id": "clinical_note_phi_review_packet",
        "name": "Clinical Note PHI Review Packet",
        "track": "policy_privacy_human_review",
        "domain": "Healthcare/Public Health",
        "topology": "branch_gate",
        "complexity": "complex",
        "subject": "clinical note PHI review evidence",
        "input_modalities": ["text", "json", "table"],
        "output_modalities": ["redacted_text", "review_packet", "audit_log"],
        "primary_inputs": ["clinical note text export", "encounter metadata JSON", "PHI policy table"],
        "external_systems": ["secure note archive", "privacy review queue"],
        "scenario": "Detect PHI, redact deterministic fields, and route ambiguous clinical notes for human review.",
    },
    {
        "pipeline_id": "financial_transaction_escalation_review",
        "name": "Financial Transaction Escalation Review",
        "track": "policy_privacy_human_review",
        "domain": "Finance/Risk",
        "topology": "branch_gate",
        "complexity": "complex",
        "subject": "financial transaction escalation review",
        "input_modalities": ["table", "json"],
        "output_modalities": ["review_packet", "audit_log", "status"],
        "primary_inputs": ["transaction CSV", "account-risk JSON", "escalation policy table"],
        "external_systems": ["case management queue", "audit evidence bucket"],
        "scenario": "Apply policy thresholds to transaction records and escalate risky cases with evidence.",
    },
    {
        "pipeline_id": "student_record_privacy_review",
        "name": "Student Record Privacy Review",
        "track": "policy_privacy_human_review",
        "domain": "Education/Research",
        "topology": "branch_gate",
        "complexity": "medium",
        "subject": "student record privacy review",
        "input_modalities": ["table", "text", "json"],
        "output_modalities": ["redacted_table", "review_packet", "audit_log"],
        "primary_inputs": ["student record CSV", "consent statement text", "privacy policy JSON"],
        "external_systems": ["student data vault", "data steward review queue"],
        "scenario": "Redact student records for research release and route exceptions to a data steward.",
    },
    {
        "pipeline_id": "access_entitlement_recertification",
        "name": "Access Entitlement Recertification",
        "track": "policy_privacy_human_review",
        "domain": "AI Platform Operations",
        "topology": "fan_in",
        "complexity": "very_complex",
        "subject": "access entitlement recertification",
        "input_modalities": ["json", "table"],
        "output_modalities": ["review_packet", "audit_log", "status"],
        "primary_inputs": ["identity provider export", "resource entitlement CSV", "manager directory JSON"],
        "external_systems": ["identity governance fixture", "manager approval queue"],
        "scenario": "Fuse identity and resource entitlement records, route recertification decisions, and preserve an audit trail.",
    },
    {
        "pipeline_id": "supplier_compliance_evidence_review",
        "name": "Supplier Compliance Evidence Review",
        "track": "policy_privacy_human_review",
        "domain": "Supply Chain/Manufacturing",
        "topology": "fan_in",
        "complexity": "complex",
        "subject": "supplier compliance evidence review",
        "input_modalities": ["pdf", "table", "json"],
        "output_modalities": ["review_packet", "risk_report", "audit_log"],
        "primary_inputs": ["supplier certificate PDF", "supplier master CSV", "compliance policy JSON"],
        "external_systems": ["supplier evidence store", "compliance review queue"],
        "scenario": "Prepare supplier evidence packets, verify policy coverage, and route gaps for review.",
    },
    # Diversity-40: complex mixed-domain workflows (5)
    {
        "pipeline_id": "disaster_response_data_fusion",
        "name": "Disaster Response Data Fusion",
        "track": "complex_mixed_domain",
        "domain": "Public Sector/Geospatial",
        "topology": "fan_out_fan_in",
        "complexity": "very_complex",
        "subject": "disaster response operational picture",
        "input_modalities": ["image", "geojson", "json", "table", "text"],
        "output_modalities": ["geojson", "briefing_packet", "alert_digest"],
        "primary_inputs": ["damage imagery", "shelter status JSON", "road closure CSV", "incident notes text"],
        "external_systems": ["emergency data lake", "operations briefing channel"],
        "scenario": "Fuse multimodal disaster-response evidence into an auditable operational picture.",
    },
    {
        "pipeline_id": "smart_city_incident_routing",
        "name": "Smart City Incident Routing",
        "track": "complex_mixed_domain",
        "domain": "Public Sector/Geospatial",
        "topology": "fan_out_fan_in",
        "complexity": "complex",
        "subject": "smart-city incident routing context",
        "input_modalities": ["json", "image", "time_series", "table"],
        "output_modalities": ["work_order", "geojson", "audit_log"],
        "primary_inputs": ["citizen report JSON", "street image attachment", "sensor window CSV", "asset registry table"],
        "external_systems": ["municipal service queue", "asset management staging"],
        "scenario": "Combine report, image, sensor, and asset evidence to route municipal incidents.",
    },
    {
        "pipeline_id": "supply_chain_disruption_triage",
        "name": "Supply Chain Disruption Triage",
        "track": "complex_mixed_domain",
        "domain": "Supply Chain/Manufacturing",
        "topology": "fan_out_fan_in",
        "complexity": "complex",
        "subject": "supply-chain disruption triage",
        "input_modalities": ["json", "table", "text"],
        "output_modalities": ["risk_report", "review_packet", "notification"],
        "primary_inputs": ["shipment status JSON", "supplier capacity CSV", "news alert text"],
        "external_systems": ["control tower staging", "procurement notification queue"],
        "scenario": "Fuse shipment, supplier, and external alert evidence to prioritize disruption responses.",
    },
    {
        "pipeline_id": "research_data_lake_publication_gate",
        "name": "Research Data Lake Publication Gate",
        "track": "complex_mixed_domain",
        "domain": "Science/Biotechnology",
        "topology": "branch_gate",
        "complexity": "very_complex",
        "subject": "research data lake publication package",
        "input_modalities": ["table", "json", "pdf", "text"],
        "output_modalities": ["publication_manifest", "review_packet", "audit_log"],
        "primary_inputs": ["experiment dataset CSV", "metadata JSON", "protocol PDF", "license statement text"],
        "external_systems": ["research data lake", "publication approval queue"],
        "scenario": "Validate research data packages, enforce publication policy, and route approval exceptions.",
    },
    {
        "pipeline_id": "public_benefits_case_review_notification",
        "name": "Public Benefits Case Review Notification",
        "track": "complex_mixed_domain",
        "domain": "Public Sector/Geospatial",
        "topology": "branch_gate",
        "complexity": "complex",
        "subject": "public-benefits case review notification",
        "input_modalities": ["table", "json", "pdf", "text"],
        "output_modalities": ["review_packet", "notification", "audit_log"],
        "primary_inputs": ["benefits application CSV", "eligibility rule JSON", "supporting document PDF", "case note text"],
        "external_systems": ["case review queue", "applicant notification endpoint"],
        "scenario": "Prepare eligibility review packets and notification records from mixed case evidence.",
    },
    # AI/NLP-10
    {
        "pipeline_id": "pdf_policy_corpus_ingestion",
        "name": "PDF Policy Corpus Ingestion",
        "track": "ai_llm_nlp",
        "domain": "Legal/Compliance",
        "topology": "staged",
        "complexity": "very_complex",
        "subject": "PDF policy corpus vector index",
        "input_modalities": ["pdf", "text", "json"],
        "output_modalities": ["vector_index", "manifest", "quality_report"],
        "primary_inputs": ["policy PDF folder", "policy metadata JSON", "chunking configuration"],
        "external_systems": ["document corpus bucket", "vector index staging"],
        "scenario": "Load policy PDFs, extract text, chunk content, embed chunks, and publish an index manifest.",
    },
    {
        "pipeline_id": "contract_clause_risk_extraction",
        "name": "Contract Clause Risk Extraction",
        "track": "ai_llm_nlp",
        "domain": "Legal/Compliance",
        "topology": "branch_gate",
        "complexity": "very_complex",
        "subject": "contract clause risk extraction",
        "input_modalities": ["pdf", "text", "json"],
        "output_modalities": ["json", "review_packet", "risk_report"],
        "primary_inputs": ["contract PDF bundle", "clause taxonomy JSON", "risk policy table"],
        "external_systems": ["contract archive", "legal review queue"],
        "scenario": "Extract contract clauses, classify risk, and route high-risk or low-confidence clauses for review.",
    },
    {
        "pipeline_id": "clinical_note_deidentification_summary",
        "name": "Clinical Note De-identification Summary",
        "track": "ai_llm_nlp",
        "domain": "Healthcare/Public Health",
        "topology": "branch_gate",
        "complexity": "very_complex",
        "subject": "clinical note de-identification and summary",
        "input_modalities": ["text", "json", "table"],
        "output_modalities": ["redacted_text", "summary", "review_packet"],
        "primary_inputs": ["clinical note text", "encounter metadata JSON", "de-identification policy table"],
        "external_systems": ["secure note bucket", "clinical reviewer queue"],
        "scenario": "De-identify clinical notes, summarize safe content, and route uncertain PHI cases.",
    },
    {
        "pipeline_id": "scientific_literature_screening",
        "name": "Scientific Literature Screening",
        "track": "ai_llm_nlp",
        "domain": "Science/Biotechnology",
        "topology": "fan_out_fan_in",
        "complexity": "complex",
        "subject": "scientific literature screening packet",
        "input_modalities": ["pdf", "text", "json"],
        "output_modalities": ["table", "review_packet", "summary"],
        "primary_inputs": ["article PDF bundle", "screening criteria JSON", "reviewer roster table"],
        "external_systems": ["literature corpus bucket", "review management queue"],
        "scenario": "Screen article PDFs against eligibility criteria and create reviewer packets.",
    },
    {
        "pipeline_id": "support_ticket_semantic_routing",
        "name": "Support Ticket Semantic Routing",
        "track": "ai_llm_nlp",
        "domain": "Marketing/Customer Operations",
        "topology": "branch_gate",
        "complexity": "very_complex",
        "subject": "support ticket semantic routing",
        "input_modalities": ["text", "json", "table"],
        "output_modalities": ["routing_decision", "summary", "audit_log"],
        "primary_inputs": ["ticket text export", "customer metadata JSON", "team routing table"],
        "external_systems": ["support ticket queue", "knowledge-base index fixture"],
        "scenario": "Embed support tickets, retrieve policy context, classify intent, and route tickets.",
    },
    {
        "pipeline_id": "multimodal_product_listing_ai_enrichment",
        "name": "Multimodal Product Listing AI Enrichment",
        "track": "ai_llm_nlp",
        "domain": "Retail/E-commerce",
        "topology": "fan_out_fan_in",
        "complexity": "complex",
        "subject": "multimodal product listing AI enrichment",
        "input_modalities": ["image", "text", "json", "table"],
        "output_modalities": ["listing_summary", "json", "quality_report"],
        "primary_inputs": ["product images", "seller description text", "category taxonomy JSON", "attribute table"],
        "external_systems": ["catalog media bucket", "listing enrichment staging"],
        "scenario": "Combine product images and text to extract attributes and generate listing summaries.",
    },
    {
        "pipeline_id": "invoice_pdf_extraction_reconciliation",
        "name": "Invoice PDF Extraction Reconciliation",
        "track": "ai_llm_nlp",
        "domain": "Finance/Risk",
        "topology": "fan_in",
        "complexity": "complex",
        "subject": "invoice PDF extraction and reconciliation",
        "input_modalities": ["pdf", "table", "json"],
        "output_modalities": ["table", "exception_report", "audit_log"],
        "primary_inputs": ["invoice PDF bundle", "purchase order CSV", "vendor registry JSON"],
        "external_systems": ["invoice document store", "accounts payable review queue"],
        "scenario": "Extract invoice fields from PDFs and reconcile them with purchase orders.",
    },
    {
        "pipeline_id": "rag_answer_pack_builder",
        "name": "RAG Answer Pack Builder",
        "track": "ai_llm_nlp",
        "domain": "AI Platform Operations",
        "topology": "fan_out_fan_in",
        "complexity": "very_complex",
        "subject": "retrieval augmented answer pack",
        "input_modalities": ["pdf", "text", "json"],
        "output_modalities": ["vector_index", "answer_pack", "evaluation_report"],
        "primary_inputs": ["source document folder", "test question JSON", "retrieval configuration"],
        "external_systems": ["document corpus bucket", "vector index fixture", "answer evaluation store"],
        "scenario": "Build a small RAG index, run retrieval test queries, and generate grounded answer packs.",
    },
    {
        "pipeline_id": "compliance_evidence_summarizer",
        "name": "Compliance Evidence Summarizer",
        "track": "ai_llm_nlp",
        "domain": "Legal/Compliance",
        "topology": "fan_in",
        "complexity": "very_complex",
        "subject": "compliance evidence summary",
        "input_modalities": ["pdf", "text", "json", "table"],
        "output_modalities": ["summary", "control_mapping", "review_packet"],
        "primary_inputs": ["evidence document bundle", "control framework JSON", "audit request table"],
        "external_systems": ["audit evidence store", "compliance review queue"],
        "scenario": "Retrieve relevant evidence, map it to controls, summarize findings, and route gaps.",
    },
    {
        "pipeline_id": "meeting_transcript_action_extraction",
        "name": "Meeting Transcript Action Extraction",
        "track": "ai_llm_nlp",
        "domain": "Education/Research",
        "topology": "staged",
        "complexity": "very_complex",
        "subject": "meeting transcript decisions and actions",
        "input_modalities": ["text", "json", "table"],
        "output_modalities": ["action_register", "summary", "notification"],
        "primary_inputs": ["meeting transcript text", "participant roster CSV", "project metadata JSON"],
        "external_systems": ["collaboration archive", "task notification staging"],
        "scenario": "Segment meeting transcripts, extract decisions and actions, assign owners, and publish follow-up records.",
    },
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def step(step_id: str, objective: str) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "name": step_id.replace("_", " ").title(),
        "objective": objective,
        "mechanism": "python_callable",
        "inputs": [],
        "outputs": [],
        "external_system_refs": [],
        "parameters": [],
        "env_infra": {"env_vars": [], "mounts": [], "network": None, "other": []},
        "failure_handling": {
            "retries": 2,
            "retry_delay": "PT5M",
            "timeout": None,
            "alerts": [],
            "idempotency": ["deterministic fixture-backed batch input"],
        },
    }


def base_steps(record: dict[str, Any]) -> list[dict[str, Any]]:
    subject = record["subject"]
    track = record["track"]
    topology = record["topology"]

    if topology == "fan_in":
        steps = [
            step("ingest_primary_source", f"Ingest the primary source for {subject}."),
            step("ingest_secondary_source", f"Ingest the secondary source for {subject}."),
            step("ingest_reference_source", f"Ingest reference data needed to interpret {subject}."),
            step("validate_source_contracts", f"Validate schemas, identities, and freshness constraints across all {subject} sources."),
            step("normalize_sources", f"Normalize source-specific fields into a shared representation for {subject}."),
            step("fuse_sources", f"Fuse normalized sources into a coherent {subject} artifact."),
            step("publish_outputs", f"Publish the prepared {subject} outputs and completion status."),
        ]
    elif topology == "fan_out":
        steps = [
            step("ingest_source_batch", f"Ingest the bounded input batch for {subject}."),
            step("validate_source_contract", f"Validate file/API contracts and required identifiers for {subject}."),
            step("extract_branch_features", f"Extract core features or text fields for {subject}."),
            step("enrich_branch_context", f"Enrich {subject} with reference metadata."),
            step("score_branch_quality", f"Score quality, risk, or confidence signals for {subject}."),
            step("merge_branch_outputs", f"Merge parallel branch outputs for {subject}."),
            step("publish_outputs", f"Publish merged {subject} outputs and completion status."),
        ]
    elif topology == "fan_out_fan_in":
        steps = [
            step("ingest_source_batch", f"Ingest all bounded inputs for {subject}."),
            step("validate_source_contract", f"Validate contracts, identifiers, and modality assumptions for {subject}."),
            step("normalize_partition_a", f"Normalize the first partition or modality for {subject}."),
            step("normalize_partition_b", f"Normalize the second partition or modality for {subject}."),
            step("normalize_partition_c", f"Normalize the third partition or modality for {subject}."),
            step("fuse_partitions", f"Fuse normalized partitions into a unified {subject} representation."),
            step("publish_outputs", f"Publish the fused {subject} outputs and completion status."),
        ]
    elif topology == "branch_gate":
        steps = [
            step("ingest_source_batch", f"Ingest the bounded input batch for {subject}."),
            step("validate_source_contract", f"Validate required fields, identities, and policy inputs for {subject}."),
            step("evaluate_policy_or_risk", f"Evaluate quality, policy, risk, or confidence rules for {subject}."),
            step("route_approved_records", f"Route approved or low-risk {subject} records."),
            step("route_exception_records", f"Route exception, high-risk, or low-confidence {subject} records."),
            step("merge_route_outcomes", f"Merge routed outcomes into a complete {subject} disposition artifact."),
            step("publish_outputs", f"Publish {subject} outputs, review status, and completion metadata."),
        ]
    elif topology == "windowed_batch":
        steps = [
            step("ingest_bounded_events", f"Ingest a finite event, log, sensor, or snapshot batch for {subject}."),
            step("validate_checkpoint_inputs", f"Validate batch boundaries, checkpoint references, and required identifiers for {subject}."),
            step("sort_and_deduplicate_records", f"Sort and deduplicate records before window or checkpoint processing for {subject}."),
            step("build_analysis_windows", f"Build deterministic windows, sessions, or snapshot intervals for {subject}."),
            step("compute_window_metrics", f"Compute metrics, state transitions, or anomaly features for {subject}."),
            step("publish_outputs", f"Publish the bounded-window {subject} outputs and checkpoint manifest."),
        ]
    else:
        steps = [
            step("ingest_source_batch", f"Ingest all bounded inputs for {subject}."),
            step("validate_source_contract", f"Validate required schemas, identifiers, and modality assumptions for {subject}."),
            step("stage_raw_artifacts", f"Stage validated raw artifacts for auditable {subject} processing."),
            step("normalize_records", f"Normalize staged records and derived fields for {subject}."),
            step("publish_outputs", f"Publish prepared {subject} outputs and completion status."),
        ]

    extras_by_track = {
        "image_document_multimodal": [
            step("extract_visual_text_features", f"Extract OCR text, visual metadata, or layout features from {subject}."),
            step("join_reference_metadata", f"Join {subject} features with reference metadata."),
            step("assess_multimodal_quality", f"Assess visual, document, and metadata quality for {subject}."),
            step("create_low_confidence_review_packet", f"Create a review packet for low-confidence {subject} records."),
            step("redact_sensitive_regions", f"Redact sensitive visual or document regions when policy requires it for {subject}."),
            step("write_evidence_manifest", f"Write an evidence manifest linking source assets to {subject} outputs."),
            step("notify_review_or_publication_target", f"Notify the configured review or publication target for {subject}."),
            step("archive_source_evidence", f"Archive source evidence references for {subject}."),
        ],
        "api_json_table_fusion": [
            step("flatten_nested_payloads", f"Flatten nested API payloads for {subject}."),
            step("join_tabular_reference_data", f"Join flattened payloads with tabular reference data for {subject}."),
            step("reconcile_conflicting_values", f"Reconcile conflicting API and table values for {subject}."),
            step("route_join_exceptions", f"Route unresolved join exceptions for {subject}."),
            step("write_reconciliation_audit", f"Write reconciliation audit evidence for {subject}."),
            step("notify_data_owner", f"Notify the data owner about {subject} publication status."),
        ],
        "time_series_sensor_window": [
            step("align_time_index", f"Align timestamps, station/device identities, and calendar boundaries for {subject}."),
            step("fill_small_gaps", f"Fill or flag small temporal gaps in {subject}."),
            step("detect_window_anomalies", f"Detect anomalies or threshold breaches in {subject}."),
            step("create_feature_manifest", f"Create a feature and quality manifest for {subject}."),
            step("route_anomaly_digest", f"Route anomaly digests for {subject}."),
            step("write_temporal_quality_report", f"Write temporal quality evidence for {subject}."),
        ],
        "event_checkpoint_windowed_batch": [
            step("load_previous_checkpoint", f"Load the previous checkpoint or snapshot for {subject}."),
            step("apply_batch_to_checkpoint", f"Apply the finite batch to checkpoint state for {subject}."),
            step("quarantine_late_or_invalid_records", f"Quarantine late, duplicate, or policy-invalid records for {subject}."),
            step("write_new_checkpoint_manifest", f"Write the new checkpoint manifest for {subject}."),
            step("create_replay_audit_log", f"Create replay audit evidence for {subject}."),
            step("notify_checkpoint_owner", f"Notify owners about checkpoint processing for {subject}."),
        ],
        "policy_privacy_human_review": [
            step("detect_sensitive_fields", f"Detect sensitive, regulated, or policy-controlled fields in {subject}."),
            step("apply_redaction_or_suppression", f"Apply redaction, suppression, or minimization rules for {subject}."),
            step("create_human_review_packet", f"Create a human-review packet for ambiguous {subject} records."),
            step("record_policy_decision", f"Record machine-readable policy decisions for {subject}."),
            step("write_audit_log", f"Write audit evidence for {subject}."),
            step("notify_reviewer_or_owner", f"Notify reviewers or data owners about {subject}."),
        ],
        "complex_mixed_domain": [
            step("standardize_cross_domain_entities", f"Standardize cross-domain entities for {subject}."),
            step("resolve_entity_conflicts", f"Resolve entity conflicts across modalities and systems for {subject}."),
            step("score_operational_priority", f"Score operational priority or risk for {subject}."),
            step("apply_publication_or_routing_gate", f"Apply publication, routing, or escalation gates for {subject}."),
            step("create_stakeholder_packet", f"Create stakeholder packets for {subject}."),
            step("publish_notifications", f"Publish notifications or work-order records for {subject}."),
            step("write_end_to_end_audit_manifest", f"Write end-to-end audit evidence for {subject}."),
        ],
        "ai_llm_nlp": [
            step("extract_or_parse_text", f"Extract, parse, or transcribe text for {subject}."),
            step("chunk_documents", f"Chunk documents or transcript segments for {subject}."),
            step("generate_embeddings", f"Generate embeddings for chunks or text spans in {subject}."),
            step("write_vector_index", f"Write or update a fixture-backed vector index for {subject}."),
            step("retrieve_grounding_context", f"Retrieve grounding context for {subject}."),
            step("run_structured_extraction", f"Run structured extraction, classification, or summarization for {subject}."),
            step("score_confidence_and_policy", f"Score confidence, grounding, and policy constraints for {subject}."),
            step("create_human_review_packet", f"Create review packets for low-confidence or high-risk {subject} outputs."),
            step("write_model_audit_manifest", f"Write model, prompt, and provenance audit evidence for {subject}."),
            step("publish_evaluation_report", f"Publish evaluation or quality reports for {subject}."),
        ],
    }

    target_count = TARGET_STEP_COUNTS[record["complexity"]]
    extras = extras_by_track[track]
    extra_index = 0
    while len(steps) < target_count:
        candidate = extras[extra_index % len(extras)]
        extra_index += 1
        existing = {item["step_id"] for item in steps}
        if candidate["step_id"] not in existing:
            if record["topology"] == "branch_gate":
                insert_at = next(
                    index
                    for index, item in enumerate(steps)
                    if item["step_id"] == "evaluate_policy_or_risk"
                )
                steps.insert(insert_at, candidate)
            else:
                steps.insert(-1, candidate)
    return steps


def control_flow(record: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    step_ids = [item["step_id"] for item in steps]
    topology = record["topology"]
    edges: list[dict[str, str]] = []
    parallel_groups: list[dict[str, Any]] = []
    branch_points: list[dict[str, Any]] = []
    gates: list[dict[str, Any]] = []

    def add_linear(start_index: int = 0) -> None:
        for source, target in zip(step_ids[start_index:], step_ids[start_index + 1 :]):
            edges.append({"from": source, "to": target})

    if topology == "fan_in":
        sources = ["ingest_primary_source", "ingest_secondary_source", "ingest_reference_source"]
        for source in sources:
            edges.append({"from": source, "to": "validate_source_contracts"})
        chain = ["validate_source_contracts"] + [item for item in step_ids if item not in sources and item != "validate_source_contracts"]
        for source, target in zip(chain, chain[1:]):
            edges.append({"from": source, "to": target})
        parallel_groups.append({"group_id": "source_fanin", "steps": sources})
    elif topology in {"fan_out", "fan_out_fan_in"}:
        branch_steps = (
            ["extract_branch_features", "enrich_branch_context", "score_branch_quality"]
            if topology == "fan_out"
            else ["normalize_partition_a", "normalize_partition_b", "normalize_partition_c"]
        )
        merge_step = "merge_branch_outputs" if topology == "fan_out" else "fuse_partitions"
        edges.append({"from": "ingest_source_batch", "to": "validate_source_contract"})
        for branch_step in branch_steps:
            edges.append({"from": "validate_source_contract", "to": branch_step})
            edges.append({"from": branch_step, "to": merge_step})
        remainder = [item for item in step_ids if item not in {"ingest_source_batch", "validate_source_contract", *branch_steps, merge_step}]
        chain = [merge_step] + remainder
        for source, target in zip(chain, chain[1:]):
            edges.append({"from": source, "to": target})
        parallel_groups.append({"group_id": "parallel_feature_branches", "steps": branch_steps})
    elif topology == "branch_gate":
        decision_index = step_ids.index("evaluate_policy_or_risk")
        pre_decision_chain = step_ids[: decision_index + 1]
        for source, target in zip(pre_decision_chain, pre_decision_chain[1:]):
            edges.append({"from": source, "to": target})
        edges.extend(
            [
                {"from": "evaluate_policy_or_risk", "to": "route_approved_records"},
                {"from": "evaluate_policy_or_risk", "to": "route_exception_records"},
                {"from": "route_approved_records", "to": "merge_route_outcomes"},
                {"from": "route_exception_records", "to": "merge_route_outcomes"},
            ]
        )
        merge_index = step_ids.index("merge_route_outcomes")
        remainder = step_ids[merge_index + 1 :]
        chain = ["merge_route_outcomes"] + remainder
        for source, target in zip(chain, chain[1:]):
            edges.append({"from": source, "to": target})
        branch_points.append(
            {
                "step_id": "evaluate_policy_or_risk",
                "branches": ["route_approved_records", "route_exception_records"],
                "condition": "policy, risk, confidence, or quality decision",
            }
        )
        gates.append({"step_id": "evaluate_policy_or_risk", "gate_type": "policy_or_quality_gate"})
    else:
        add_linear()
        if topology == "windowed_batch":
            gates.append({"step_id": "validate_checkpoint_inputs", "gate_type": "checkpoint_boundary"})

    return {
        "edges": edges,
        "parallel_groups": parallel_groups,
        "branch_points": branch_points,
        "gates": gates,
    }


def description(record: dict[str, Any], steps: list[dict[str, Any]], flow: dict[str, Any]) -> str:
    lines = [
        "Pipeline Summary:",
        f"- Pipeline ID: extension-v1__{record['pipeline_id']}.py",
        f"- Name: {record['name']}",
        f"- Purpose: {record['scenario']}",
        "- Execution model: bounded batch",
        f"- Extension track: {record['track']}",
        f"- Topology pattern: {record['topology']}",
        f"- Complexity band: {record['complexity']}",
        f"- Business domain: {record['domain']}",
        f"- Input modalities: {', '.join(record['input_modalities'])}",
        f"- Output modalities: {', '.join(record['output_modalities'])}",
        "- Notes: Synthetic Extension-50 source; use only as benchmark input and not as hidden gold evidence.",
        "",
        "Primary Inputs:",
        *[f"- {item}" for item in record["primary_inputs"]],
        "",
        "External Systems:",
        *[f"- {item} (fixture-backed; no production system is contacted)" for item in record["external_systems"]],
        "",
        "Control Flow:",
        "- Dependencies (directed edges):",
        *[f"  - {edge['from']} -> {edge['to']}" for edge in flow["edges"]],
        "",
        "Data Artifacts / I-O Identifiers:",
        "- source_bundle: fixture-backed source input bundle",
        "- prepared_outputs: validated workflow output bundle",
        "- audit_manifest: provenance, checksum, quality, and routing evidence",
        "",
        "Pipeline Steps:",
    ]
    for index, item in enumerate(steps, start=1):
        lines.extend(
            [
                f"{index}. {item['step_id']} - {item['name']}",
                f"  - Objective: {item['objective']}",
                "  - Mechanism: python_callable",
                "  - Failure handling:",
                "    - retries: 2",
                "    - retry delay: PT5M",
            ]
        )
    lines.extend(["", "Scheduling:", "- Schedule type: manual", "- Catchup/backfill: False", ""])
    return "\n".join(lines)


def spec(record: dict[str, Any], steps: list[dict[str, Any]], flow: dict[str, Any]) -> dict[str, Any]:
    return {
        "spec_version": "1.0",
        "corpus": "Prompt2ServiceFlow Extension-50",
        "corpus_version": "extension_v1",
        "pipeline_id": record["pipeline_id"],
        "pipeline_name": record["name"],
        "source": {
            "unique_key": None,
            "repo": "prompt2serviceflow-extension-v1",
            "file_path": f"synthetic/{record['pipeline_id']}.py",
            "repo_url": None,
            "detected_airflow_version": "2.x",
            "sampled_version": None,
            "sampled_commit": None,
            "sampled_time": None,
            "source_fingerprint_sha256": None,
            "source_type": "synthetic_provenance_marked",
        },
        "summary": {
            "purpose": record["scenario"],
            "business_domain": record["domain"],
            "execution_model": "bounded_batch",
            "topology_pattern": record["topology"],
            "extension_track": record["track"],
            "complexity_band": record["complexity"],
            "input_modalities": record["input_modalities"],
            "output_modalities": record["output_modalities"],
            "notes": "Synthetic Extension-50 source package. No hidden gold annotations are included.",
        },
        "schedule": {
            "schedule_type": "manual",
            "schedule_expression": None,
            "timezone": None,
            "start_date": None,
            "catchup_backfill": False,
        },
        "control_flow": flow,
        "external_systems": [
            {
                "type": "fixture_backed_system",
                "name": system,
                "identifier": f"synthetic://extension-v1/{record['pipeline_id']}/{index}",
                "details": ["No production system is contacted."],
                "auth": [],
            }
            for index, system in enumerate(record["external_systems"], start=1)
        ],
        "data_artifacts": {
            "files": [
                {"identifier": "source_bundle", "description": "Fixture-backed source input bundle"},
                {"identifier": "prepared_outputs", "description": "Validated workflow output bundle"},
                {"identifier": "audit_manifest", "description": "Provenance, checksum, quality, and routing evidence"},
            ],
            "tables": [],
            "buckets": [],
            "topics": [],
            "modalities": record["input_modalities"],
        },
        "steps": steps,
    }


def write_batch(batch: int, records: list[dict[str, Any]]) -> None:
    batch_root = OUTPUT_ROOT / f"batch_{batch:02d}"
    descriptions = batch_root / "descriptions"
    specs = batch_root / "specs"
    descriptions.mkdir(parents=True, exist_ok=True)
    specs.mkdir(parents=True, exist_ok=True)

    for number, record in enumerate(records, start=1):
        steps = base_steps(record)
        flow = control_flow(record, steps)
        stem = f"{record['global_number']:02d}_{record['pipeline_id']}"
        description_path = descriptions / f"{stem}.txt"
        spec_path = specs / f"{stem}.json"
        description_path.write_text(description(record, steps, flow), encoding="utf-8")
        spec_path.write_text(json.dumps(spec(record, steps, flow), indent=2) + "\n", encoding="utf-8")
        record.update(
            {
                "batch_number": number,
                "description_path": str(description_path.relative_to(OUTPUT_ROOT)),
                "spec_path": str(spec_path.relative_to(OUTPUT_ROOT)),
                "step_count": len(steps),
                "edge_count": len(flow["edges"]),
                "parallel_group_count": len(flow["parallel_groups"]),
                "branch_point_count": len(flow["branch_points"]),
                "gate_count": len(flow["gates"]),
            }
        )

    (batch_root / "manifest.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    checksums = [
        f"{sha256(path)}  {path.relative_to(batch_root)}"
        for path in sorted(batch_root.rglob("*.txt")) + sorted(batch_root.rglob("*.json"))
    ]
    (batch_root / "checksums.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8")


def summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "corpus": "Prompt2ServiceFlow Extension-50",
        "corpus_version": "extension_v1",
        "pipeline_count": len(records),
        "frozen_baseline_policy": "Frozen-60 artifacts are not mutated by this package.",
        "track_counts": dict(sorted(Counter(record["track"] for record in records).items())),
        "complexity_counts": dict(sorted(Counter(record["complexity"] for record in records).items())),
        "topology_counts": dict(sorted(Counter(record["topology"] for record in records).items())),
        "domain_counts": dict(sorted(Counter(record["domain"] for record in records).items())),
        "minimum_step_count": min(record["step_count"] for record in records),
        "maximum_step_count": max(record["step_count"] for record in records),
        "batches": 10,
        "batch_size": 5,
    }


def write_docs(records: list[dict[str, Any]]) -> None:
    stats = summary(records)
    readme = [
        "# Extension-50 Source Package",
        "",
        "This package contains 50 synthetic, provenance-marked source descriptions for the Prompt2ServiceFlow Extension-50 plan.",
        "",
        "It intentionally does not mutate the Frozen-60 baseline. It contains only source descriptions, companion source specifications, manifests, and checksums. It does not contain ServiceFlowIR, service bindings, candidate labels, artifact mappings, mock implementations, Argo outputs, or hidden gold.",
        "",
        "## Composition",
        "",
        f"- Total pipelines: {stats['pipeline_count']}",
        "- Batches: 10 batches of 5 pipelines",
        f"- Minimum source tasks per pipeline: {stats['minimum_step_count']}",
        f"- Maximum source tasks per pipeline: {stats['maximum_step_count']}",
        "",
        "### Track Counts",
        "",
        *[f"- {track}: {count}" for track, count in stats["track_counts"].items()],
        "",
        "### Complexity Counts",
        "",
        *[f"- {band}: {count}" for band, count in stats["complexity_counts"].items()],
        "",
        "## Intended Use",
        "",
        "Use these sources as the starting point for Extension-50 review, catalog-gap analysis, ServiceFlowIR annotation, service binding, mock construction, Argo generation, semantic hardening, and independent adjudication.",
        "",
    ]
    (OUTPUT_ROOT / "README.md").write_text("\n".join(readme), encoding="utf-8")

    generation = [
        "# Generation Record",
        "",
        "- corpus: Prompt2ServiceFlow Extension-50",
        "- corpus version: extension_v1",
        "- source type: synthetic, deterministic, provenance-marked",
        "- generator: `scripts/create_extension_50_sources.py`",
        "- generated content: public descriptions and reviewer companion source specifications",
        "- prohibited content: hidden gold annotations, candidate labels, service bindings, ServiceFlowIR, runtime mocks, Argo outputs",
        "- frozen baseline policy: Frozen-60 artifacts are not mutated",
        "- streaming policy: true streaming is excluded; event/checkpoint/window cases are bounded batch workflows",
        "",
    ]
    (OUTPUT_ROOT / "GENERATION.md").write_text("\n".join(generation), encoding="utf-8")

    (OUTPUT_ROOT / "summary.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)
    OUTPUT_ROOT.mkdir(parents=True)

    records: list[dict[str, Any]] = []
    for index, item in enumerate(BLUEPRINTS, start=1):
        record = dict(item)
        record["global_number"] = index
        record["batch"] = ((index - 1) // 5) + 1
        record["source_type"] = "SyntheticExtension"
        record["source_family"] = "Prompt2ServiceFlow Extension v1"
        records.append(record)

    for batch in range(1, 11):
        write_batch(batch, [record for record in records if record["batch"] == batch])

    (OUTPUT_ROOT / "manifest.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    write_docs(records)

    checksums = [
        f"{sha256(path)}  {path.relative_to(OUTPUT_ROOT)}"
        for path in sorted(OUTPUT_ROOT.rglob("*.txt"))
        + sorted(OUTPUT_ROOT.rglob("*.json"))
        + sorted(OUTPUT_ROOT.rglob("*.md"))
        if path.name != "checksums.sha256"
    ]
    (OUTPUT_ROOT / "checksums.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print(f"created {len(records)} Extension-50 source pipelines in {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
