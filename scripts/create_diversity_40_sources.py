#!/usr/bin/env python3
"""Create the synthetic, provenance-marked Diversity-40 source corpus."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "benchmark" / "source" / "diversity_v1"

# batch, id, name, domain, topology, complexity
BLUEPRINTS = [
    (1, "energy_meter_daily_normalization", "Energy Meter Daily Normalization", "Environmental/Energy", "linear", "simple"),
    (1, "clinic_referral_extract", "Clinic Referral Extract", "Healthcare/Public Health", "linear", "simple"),
    (1, "retail_price_snapshot", "Retail Price Snapshot", "Retail/E-commerce", "linear", "simple"),
    (1, "grant_payment_register", "Grant Payment Register", "Public Sector/Geospatial", "linear", "simple"),
    (1, "customer_consent_refresh", "Customer Consent Refresh", "Marketing/Customer Operations", "linear", "simple"),
    (1, "lab_sample_metadata_load", "Lab Sample Metadata Load", "Science/Biotechnology", "linear", "simple"),
    (1, "invoice_currency_standardization", "Invoice Currency Standardization", "Finance/Risk", "linear", "simple"),
    (1, "supplier_lead_time_profile", "Supplier Lead-Time Profile", "Supply Chain/Manufacturing", "linear", "simple"),
    (1, "energy_tariff_stage_load", "Energy Tariff Stage Load", "Environmental/Energy", "staged", "medium"),
    (1, "hospital_wait_time_stage_load", "Hospital Wait-Time Stage Load", "Healthcare/Public Health", "staged", "medium"),
    (1, "store_catalog_stage_load", "Store Catalog Stage Load", "Retail/E-commerce", "staged", "medium"),
    (1, "land_parcel_stage_load", "Land Parcel Stage Load", "Public Sector/Geospatial", "staged", "medium"),
    (1, "campaign_response_fanout", "Campaign Response Fan-out", "Marketing/Customer Operations", "fan_out", "medium"),
    (1, "genomics_qc_fanout", "Genomics Quality-Control Fan-out", "Science/Biotechnology", "fan_out", "medium"),
    (1, "risk_factor_fanout", "Risk Factor Fan-out", "Finance/Risk", "fan_out", "medium"),
    (1, "shipment_event_fanout", "Shipment Event Fan-out", "Supply Chain/Manufacturing", "fan_out", "medium"),
    (1, "energy_sensor_fanin", "Energy Sensor Fan-in", "Environmental/Energy", "fan_in", "medium"),
    (1, "patient_capacity_fanin", "Patient Capacity Fan-in", "Healthcare/Public Health", "fan_in", "medium"),
    (1, "retail_channel_fanin", "Retail Channel Fan-in", "Retail/E-commerce", "fan_in", "medium"),
    (1, "permit_exception_fanin", "Permit Exception Fan-in", "Public Sector/Geospatial", "fan_in", "medium"),
    (2, "audience_eligibility_router", "Audience Eligibility Router", "Marketing/Customer Operations", "branch_merge", "complex"),
    (2, "biobank_release_router", "Biobank Release Router", "Science/Biotechnology", "branch_merge", "complex"),
    (2, "credit_hold_router", "Credit Hold Router", "Finance/Risk", "branch_merge", "complex"),
    (2, "supplier_exception_router", "Supplier Exception Router", "Supply Chain/Manufacturing", "branch_merge", "complex"),
    (2, "energy_grid_fusion", "Energy Grid Fusion", "Environmental/Energy", "fan_out_fan_in", "complex"),
    (2, "care_pathway_fusion", "Care Pathway Fusion", "Healthcare/Public Health", "fan_out_fan_in", "complex"),
    (2, "marketplace_reconciliation_fusion", "Marketplace Reconciliation Fusion", "Retail/E-commerce", "fan_out_fan_in", "complex"),
    (2, "municipal_service_fusion", "Municipal Service Fusion", "Public Sector/Geospatial", "fan_out_fan_in", "complex"),
    (2, "marketing_attribution_fusion", "Marketing Attribution Fusion", "Marketing/Customer Operations", "fan_out_fan_in", "complex"),
    (2, "multi_omics_fusion", "Multi-Omics Fusion", "Science/Biotechnology", "fan_out_fan_in", "complex"),
    (2, "liquidity_stress_fusion", "Liquidity Stress Fusion", "Finance/Risk", "fan_out_fan_in", "complex"),
    (2, "factory_quality_fusion", "Factory Quality Fusion", "Supply Chain/Manufacturing", "fan_out_fan_in", "complex"),
    (2, "renewable_forecast_command_center", "Renewable Forecast Command Center", "Environmental/Energy", "staged", "very_complex"),
    (2, "hospital_capacity_command_center_v2", "Hospital Capacity Command Center v2", "Healthcare/Public Health", "staged", "very_complex"),
    (2, "omnichannel_inventory_command_center", "Omnichannel Inventory Command Center", "Retail/E-commerce", "fan_out", "very_complex"),
    (2, "disaster_relief_command_center", "Disaster Relief Command Center", "Public Sector/Geospatial", "fan_out", "very_complex"),
    (2, "customer_retention_command_center", "Customer Retention Command Center", "Marketing/Customer Operations", "fan_in", "very_complex"),
    (2, "bioprocess_release_command_center", "Bioprocess Release Command Center", "Science/Biotechnology", "fan_in", "very_complex"),
    (2, "portfolio_stress_command_center", "Portfolio Stress Command Center", "Finance/Risk", "branch_merge", "complex"),
    (2, "supply_network_command_center", "Supply Network Command Center", "Supply Chain/Manufacturing", "branch_merge", "complex"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def steps_for(topology: str, complexity: str) -> tuple[list[dict], list[dict], list[dict]]:
    steps = [
        {"step_id": "extract_source", "objective": "Extract the source dataset into a raw tabular artifact."},
        {"step_id": "validate_schema", "objective": "Validate required columns, formats, and record identity."},
    ]
    edges = [{"from": "extract_source", "to": "validate_schema"}]
    parallel_groups: list[dict] = []
    if topology == "linear":
        steps.extend([
            {"step_id": "transform_records", "objective": "Standardize records and derive required fields."},
            {"step_id": "publish_dataset", "objective": "Publish the validated dataset and completion status."},
        ])
        edges.extend([{"from": "validate_schema", "to": "transform_records"}, {"from": "transform_records", "to": "publish_dataset"}])
    elif topology == "staged":
        steps.extend([
            {"step_id": "stage_raw_data", "objective": "Persist validated data to an auditable staging area."},
            {"step_id": "transform_stage", "objective": "Transform staged records into the canonical data model."},
            {"step_id": "quality_gate", "objective": "Assess transformed data before promotion."},
            {"step_id": "publish_dataset", "objective": "Promote approved records to the final dataset."},
        ])
        edges.extend([{"from": "validate_schema", "to": "stage_raw_data"}, {"from": "stage_raw_data", "to": "transform_stage"}, {"from": "transform_stage", "to": "quality_gate"}, {"from": "quality_gate", "to": "publish_dataset"}])
    elif topology == "fan_out":
        branches = ["profile_records", "enrich_reference", "score_records"]
        steps.extend({"step_id": step, "objective": f"Produce the {step.replace('_', ' ')} artifact."} for step in branches)
        steps.append({"step_id": "publish_dataset", "objective": "Publish branch outputs with completion status."})
        edges.extend({"from": "validate_schema", "to": step} for step in branches)
        edges.extend({"from": step, "to": "publish_dataset"} for step in branches)
        parallel_groups = [{"group_id": "analysis_fanout", "steps": branches}]
    elif topology == "fan_in":
        sources = ["extract_primary", "extract_secondary", "extract_reference"]
        steps = [{"step_id": step, "objective": f"Extract the {step.replace('_', ' ')} dataset."} for step in sources]
        steps.extend([{ "step_id": "validate_schema", "objective": "Validate every source dataset."}, {"step_id": "merge_sources", "objective": "Merge all validated source artifacts."}, {"step_id": "publish_dataset", "objective": "Publish the merged dataset."}])
        edges = [{"from": step, "to": "validate_schema"} for step in sources]
        edges.extend([{"from": "validate_schema", "to": "merge_sources"}, {"from": "merge_sources", "to": "publish_dataset"}])
        parallel_groups = [{"group_id": "source_fanin", "steps": sources}]
    elif topology == "fan_out_fan_in":
        branches = ["normalize_a", "normalize_b", "normalize_c"]
        steps.extend({"step_id": step, "objective": f"Normalize one independent source partition ({step[-1]})."} for step in branches)
        steps.extend([{ "step_id": "fuse_partitions", "objective": "Fuse all normalized partitions through a cardinality-many input."}, {"step_id": "publish_dataset", "objective": "Publish the fused dataset."}])
        edges.extend({"from": "validate_schema", "to": step} for step in branches)
        edges.extend({"from": step, "to": "fuse_partitions"} for step in branches)
        edges.append({"from": "fuse_partitions", "to": "publish_dataset"})
        parallel_groups = [{"group_id": "normalization_fanout", "steps": branches}]
    else:
        steps.extend([{ "step_id": "calculate_decision", "objective": "Calculate a policy decision from validated records."}, {"step_id": "approve_records", "objective": "Publish records that meet the policy."}, {"step_id": "quarantine_records", "objective": "Quarantine records that fail the policy."}, {"step_id": "notify_outcome", "objective": "Notify stakeholders of the selected outcome."}])
        edges.extend([{"from": "validate_schema", "to": "calculate_decision"}, {"from": "calculate_decision", "to": "approve_records"}, {"from": "calculate_decision", "to": "quarantine_records"}, {"from": "approve_records", "to": "notify_outcome"}, {"from": "quarantine_records", "to": "notify_outcome"}])
    extra_enrichments = 3 if complexity == "complex" else 7 if complexity == "very_complex" else 0
    if extra_enrichments:
        for index in range(1, extra_enrichments + 1):
            step_id = f"audit_enrichment_{index}"
            steps.insert(-1, {"step_id": step_id, "objective": f"Apply audited enrichment stage {index}."})
            edges.append({"from": "validate_schema", "to": step_id})
    return steps, edges, parallel_groups


def description(record: dict, steps: list[dict], edges: list[dict]) -> str:
    lines = [
        "Pipeline Summary:",
        f"- Pipeline ID: diversity-v1__{record['pipeline_id']}.py",
        f"- Name: {record['pipeline_id']}",
        f"- Purpose: {record['name']} is a synthetic data-preparation workflow for {record['domain']}.",
        "- Execution model: batch",
        f"- Topology pattern: {record['topology']}",
        f"- Business domain: {record['domain']}",
        "- Notes: Synthetic Diversity-40 source; use only as benchmark input and not as hidden gold evidence.",
        "",
        "Control Flow:",
        "- Dependencies (directed edges):",
        *[f"  - {edge['from']} -> {edge['to']}" for edge in edges],
        "",
        "Data Artifacts / I-O Identifiers:",
        "- file: raw_input.csv (Synthetic input data)",
        "- file: prepared_output.parquet (Prepared output dataset)",
        "",
        "External Systems:",
        "- object_storage: Fixture-backed source and publication location",
        "",
        "Pipeline Steps:",
    ]
    for index, step in enumerate(steps, start=1):
        lines.extend([f"{index}. {step['step_id']} — {step['step_id']}", f"  - Objective: {step['objective']}", "  - Mechanism: python_callable", "  - Failure handling:", "    - retries: 2", "    - retry delay: PT5M"])
    lines.extend(["", "Scheduling:", "- Schedule type: manual", "- Catchup/backfill: False", ""])
    return "\n".join(lines)


def spec(record: dict, steps: list[dict], edges: list[dict], parallel_groups: list[dict]) -> dict:
    return {
        "spec_version": "1.0",
        "pipeline_id": record["pipeline_id"],
        "pipeline_name": record["name"],
        "source": {"unique_key": None, "repo": "prompt2serviceflow-diversity-v1", "file_path": f"synthetic/{record['pipeline_id']}.py", "repo_url": None, "detected_airflow_version": "2.x", "sampled_version": None, "sampled_commit": None, "sampled_time": None, "source_fingerprint_sha256": None},
        "summary": {"purpose": f"Synthetic data-preparation workflow for {record['domain']}", "business_domain": record["domain"], "execution_model": "batch", "topology_pattern": record["topology"], "notes": "Synthetic Diversity-40 source package."},
        "schedule": {"schedule_type": "manual", "schedule_expression": None, "timezone": None, "start_date": None, "catchup_backfill": False},
        "control_flow": {"edges": edges, "parallel_groups": parallel_groups, "branch_points": [], "gates": []},
        "external_systems": [{"type": "object_storage", "name": "Fixture-backed object storage", "identifier": "synthetic://diversity-v1", "details": ["No production system is contacted."], "auth": []}],
        "data_artifacts": {"files": [{"identifier": "raw_input.csv", "description": "Synthetic tabular input"}, {"identifier": "prepared_output.parquet", "description": "Synthetic prepared output"}], "tables": [], "buckets": [], "topics": []},
        "steps": [{"step_id": step["step_id"], "name": step["step_id"], "objective": step["objective"], "mechanism": "python_callable", "inputs": [], "outputs": [], "external_system_refs": [], "parameters": [], "env_infra": {"env_vars": [], "mounts": [], "network": None, "other": []}, "failure_handling": {"retries": 2, "retry_delay": "PT5M", "timeout": None, "alerts": [], "idempotency": []}} for step in steps],
    }


def write_batch(batch: int, records: list[dict]) -> None:
    batch_root = OUTPUT_ROOT / f"batch_{batch:02d}"
    descriptions = batch_root / "descriptions"
    specs = batch_root / "specs"
    descriptions.mkdir(parents=True)
    specs.mkdir()
    for number, record in enumerate(records, start=1):
        steps, edges, parallel_groups = steps_for(record["topology"], record["complexity"])
        stem = f"{number:02d}_{record['pipeline_id']}"
        (descriptions / f"{stem}.txt").write_text(description(record, steps, edges), encoding="utf-8")
        document = spec(record, steps, edges, parallel_groups)
        spec_path = specs / f"{stem}.json"
        spec_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        record.update({"number": number, "description_path": str((descriptions / f"{stem}.txt").relative_to(OUTPUT_ROOT)), "spec_path": str(spec_path.relative_to(OUTPUT_ROOT)), "step_count": len(steps), "edge_count": len(edges)})
    (batch_root / "manifest.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    checksums = [f"{sha256(path)}  {path.relative_to(batch_root)}" for path in sorted(batch_root.rglob("*.txt")) + sorted(batch_root.rglob("*.json"))]
    (batch_root / "checksums.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8")


def main() -> None:
    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)
    records = [{"pipeline_id": item[1], "name": item[2], "domain": item[3], "topology": item[4], "complexity": item[5], "source_type": "SyntheticDiversity", "source_family": "Prompt2ServiceFlow Diversity v1", "batch": item[0]} for item in BLUEPRINTS]
    for batch in (1, 2):
        write_batch(batch, [record for record in records if record["batch"] == batch])
    with (OUTPUT_ROOT / "README.md").open("w", encoding="utf-8") as handle:
        handle.write("# Diversity-40 Source Package\n\nThis is a synthetic, provenance-marked source corpus generated deterministically by `scripts/create_diversity_40_sources.py`. It contains public descriptions and reviewer companion specifications only; it contains no ServiceFlowIR, candidate labels, service bindings, or hidden gold.\n")
    with (OUTPUT_ROOT / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")
    with (OUTPUT_ROOT / "GENERATION.md").open("w", encoding="utf-8") as handle:
        handle.write("# Generation Record\n\n- corpus: Diversity-40\n- source type: synthetic, deterministic templates\n- generator: `scripts/create_diversity_40_sources.py`\n- intended use: extension source review before catalog and ServiceFlowIR annotation\n- prohibited use: treating these descriptions as independent human-validated gold\n")
    print(f"created {len(records)} Diversity-40 source pipelines in {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
