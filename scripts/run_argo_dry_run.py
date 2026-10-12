#!/usr/bin/env python3
"""Run offline Argo deployment-readiness evaluation for Main-40 in four batches."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVALUATOR_ROOT = Path(
    os.environ.get("P2SF_ARGO_EVALUATOR_ROOT", ROOT / "external" / "Argo_workflow_ex")
)
BATCHES: dict[int, tuple[str, ...]] = {
    1: (
        "airflow_db_cleanup",
        "airflow_log_cleanup",
        "airvisual_pipeline_lat_long_v1",
        "assignment_solution",
        "backup_strategy_selector",
        "climate_data_fusion_pipeline",
        "content_moderation_pipeline",
        "customer_dq_scoring_pipeline",
        "daily_sales_report",
        "data_quality_gate",
    ),
    2: (
        "data_transformation_pipeline",
        "database_partition_check_etl",
        "database_replication_fanout",
        "environmental_monitoring_network_v1",
        "etl_import_ensembl",
        "etl_import_mondo",
        "executive_sales_dashboard",
        "file_arrival_watcher",
        "fraud_detection_triage",
        "ftp_vendor_inventory_processor",
    ),
    3: (
        "global_dag",
        "healthcare_claims_etl",
        "hive_script",
        "keyword_extraction_pipeline",
        "magento_graphql_customer",
        "mahidol_aqi_pipeline_v2_alert_1",
        "medical_facility_accessibility_v1",
        "multi_channel_marketing_campaign",
        "multi_region_ecommerce_analytics",
        "multilingual_product_review_analysis_v1",
    ),
    4: (
        "pcd_etl",
        "pipeline_execution_dag",
        "portfolio_rebalancing_dag",
        "procurement_supplier_validation_v1",
        "regulatory_report_router",
        "retail_inventory_reconciliation",
        "runelt_alert",
        "supply_chain_shipment_etl",
        "test_dbx_aws_dag_reuse",
        "wf_main_datasets_load_l2_to_l2",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--batch", type=int, choices=sorted(BATCHES))
    group.add_argument("--all", action="store_true")
    parser.add_argument("--evaluator-root", type=Path, default=DEFAULT_EVALUATOR_ROOT)
    parser.add_argument("--output-root", type=Path, default=ROOT / "runs" / "argo_dry_run")
    return parser.parse_args()


def evaluate_manifest(evaluate_file: Any, path: Path) -> dict[str, Any]:
    # The local CLI is discovered from PATH; the runner must be invoked through .venv.
    return evaluate_file(path, skip_argo_lint=False)


def main() -> None:
    args = parse_args()
    venv_bin = str(Path(sys.executable).parent)
    os.environ["PATH"] = venv_bin + os.pathsep + os.environ.get("PATH", "")
    evaluator_root = args.evaluator_root.resolve()
    if not evaluator_root.is_dir():
        raise ValueError(f"Evaluator root does not exist: {evaluator_root}")
    sys.path.insert(0, str(evaluator_root))
    from argo_workflow_evaluator.cli import evaluate_file
    from prompt2serviceflow.compiler.argo import write_resources

    batch_numbers = sorted(BATCHES) if args.all else [args.batch]
    for batch_number in batch_numbers:
        pipeline_ids = BATCHES[batch_number]
        batch_dir = args.output_root / f"main_batch_{batch_number:02d}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        records = []
        for pipeline_id in pipeline_ids:
            instance_dir = ROOT / "benchmark" / "instances" / "main" / pipeline_id
            outputs = write_resources(instance_dir)
            manifests = [("workflow", outputs["workflow"])]
            if "cronworkflow" in outputs:
                manifests.append(("cronworkflow", outputs["cronworkflow"]))
            evaluations = []
            for manifest_type, manifest_path in manifests:
                result = evaluate_manifest(evaluate_file, manifest_path)
                result_path = batch_dir / f"{pipeline_id}.{manifest_type}.json"
                result_path.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
                evaluations.append(
                    {
                        "manifest_type": manifest_type,
                        "path": str(manifest_path.relative_to(ROOT)),
                        "result_path": str(result_path.relative_to(ROOT)),
                        "platform_gates_passed": result["summary"]["platform_gate_passed"],
                        "sat": result["summary"]["static_score"],
                        "pct": result["summary"]["compliance_score"],
                        "argo_lint": result["platform_compliance"]["metadata"]["argo_lint"]["status"],
                    }
                )
            records.append({"pipeline_id": pipeline_id, "evaluations": evaluations})
            print(f"batch {batch_number}: evaluated {pipeline_id}", flush=True)

        flattened = [evaluation for record in records for evaluation in record["evaluations"]]
        summary = {
            "evaluation_version": "0.1.0",
            "evaluation_kind": "argo_offline_deployment_readiness",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "batch": batch_number,
            "pipeline_count": len(records),
            "manifest_count": len(flattened),
            "platform_gate_passed": sum(item["platform_gates_passed"] for item in flattened),
            "argo_lint_passed": sum(item["argo_lint"] == "passed" for item in flattened),
            "records": records,
            "limitations": [
                "No Kubernetes cluster or Argo controller was contacted.",
                "This is not G5 mock execution; it is offline deployment-readiness validation.",
            ],
        }
        (batch_dir / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"batch {batch_number} summary: pipelines={len(records)} manifests={len(flattened)} "
            f"gates={summary['platform_gate_passed']}/{len(flattened)} "
            f"lint={summary['argo_lint_passed']}/{len(flattened)}",
            flush=True,
        )


if __name__ == "__main__":
    main()
