#!/usr/bin/env python3
"""Apply semantic hardening to the second Main-40 annotation batch."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any

from harden_semantic_batch_01 import (
    INSTANCES,
    ROOT,
    add_source_accounting,
    artifact,
    binding,
    configure_intent,
    load_yaml,
    rebuild_consumers,
    remove_intents,
    status_schema,
    write_json,
    write_yaml,
)


HARDENED_BENCHMARK_IDS = {
    "main:backup_strategy_selector",
    "main:fraud_detection_triage",
    "main:file_arrival_watcher",
    "main:database_replication_fanout",
    "main:multi_region_ecommerce_analytics",
}


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content).lstrip(), encoding="utf-8")


def external_artifact(
    artifact_id: str,
    name: str,
    data_type: str,
    fixture_ref: str,
    external_system_ref: str,
    *,
    media_type: str = "application/json",
    sensitivity: str = "internal",
) -> dict[str, Any]:
    result = artifact(
        artifact_id,
        name,
        data_type,
        producer=None,
        role="config",
        fixture_ref=fixture_ref,
        persistence="external",
        kind="external_resource",
        media_type=media_type,
        sensitivity=sensitivity,
    )
    result["external_system_ref"] = external_system_ref
    return result


def validation_expectations(*checks: str) -> list[dict[str, Any]]:
    return [
        {"gate": "G0", "expected_status": "pass", "checks": [checks[0]]},
        {"gate": "G1", "expected_status": "pass", "checks": [checks[1]]},
        {"gate": "G2", "expected_status": "pass", "checks": [checks[2]]},
        {"gate": "G3", "expected_status": "pass", "checks": [checks[3]]},
        {"gate": "G4", "expected_status": "pass", "checks": [checks[4]]},
        {"gate": "G5", "expected_status": "pass", "checks": [checks[5]]},
        {"gate": "G6", "expected_status": "pass", "checks": [checks[6]]},
    ]


def update_manifest_statuses() -> None:
    manifest_path = ROOT / "benchmark" / "manifest.jsonl"
    records = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    found = set()
    for record in records:
        benchmark_id = record["benchmark_id"]
        if benchmark_id in HARDENED_BENCHMARK_IDS:
            record["annotation_status"] = "semantic_hardening_complete"
            record["review_status"] = "independent_review_pending"
            found.add(benchmark_id)
    missing = sorted(HARDENED_BENCHMARK_IDS - found)
    if missing:
        raise ValueError(f"Cannot update absent manifest records: {missing}")
    manifest_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def harden_backup_strategy() -> None:
    instance = INSTANCES / "backup_strategy_selector"
    sf = load_yaml(instance / "gold" / "serviceflow.yaml")
    remove_intents(sf, {"start_backup_process", "backup_complete"})
    sf["external_systems"] = [
        {
            "system_id": "backup_database",
            "type": "database",
            "name": "Database backup target",
            "identifier": "backup_target_db",
            "access_mode": "read",
            "authentication": "secret",
            "mock_strategy": "fixture",
        }
    ]
    configure_intent(
        sf,
        "date_check_task",
        capability="Select a full or incremental backup mode from the logical execution date.",
        inputs=["execution_date"],
        outputs=["backup_strategy_decision"],
        external_system_refs=[],
        network_access="forbidden",
        secret_access="forbidden",
        rationale="The source explicitly evaluates the day of week before choosing a branch.",
        category="Transformer",
    )
    for intent_id, mode in (("full_backup_task", "full"), ("incremental_backup_task", "incremental")):
        configure_intent(
            sf,
            intent_id,
            capability=f"Create a {mode} database backup artifact for the selected branch.",
            inputs=["database_resource"],
            outputs=["backup_file", "backup_manifest", "backup_status"],
            external_system_refs=["backup_database"],
            network_access="required",
            secret_access="required",
            rationale=(
                "Both branch steps invoke the same backup capability with a different "
                "selected backup mode."
            ),
            category="Maintenance",
        )
    configure_intent(
        sf,
        "verify_backup_task",
        capability="Verify the selected backup artifact for readability, integrity, and completeness.",
        inputs=["backup_file", "backup_manifest"],
        outputs=["verification_result", "verification_status"],
        external_system_refs=[],
        network_access="forbidden",
        secret_access="forbidden",
        rationale="The source merges both backup branches into one backup-integrity check.",
        category="QualityCheck",
    )
    sf["control_flow"] = {
        "edges": [
            {
                "from": "date_check_task",
                "to": "full_backup_task",
                "condition": "backup_strategy_decision.selected_strategy == full",
            },
            {
                "from": "date_check_task",
                "to": "incremental_backup_task",
                "condition": "backup_strategy_decision.selected_strategy == incremental",
            },
            {"from": "full_backup_task", "to": "verify_backup_task"},
            {"from": "incremental_backup_task", "to": "verify_backup_task"},
        ],
        "parallel_groups": [],
        "branches": [
            {
                "branch_id": "backup_strategy",
                "decision_intent": "date_check_task",
                "decision_artifact": "backup_strategy_decision",
                "cases": [
                    {
                        "case_id": "full",
                        "condition": "backup_strategy_decision.selected_strategy == full",
                        "next_intents": ["full_backup_task"],
                    },
                    {
                        "case_id": "incremental",
                        "condition": "backup_strategy_decision.selected_strategy == incremental",
                        "next_intents": ["incremental_backup_task"],
                    },
                ],
                "merge_intent": "verify_backup_task",
            }
        ],
        "gates": [],
    }
    sf["artifacts"] = [
        external_artifact(
            "execution_date",
            "Execution date",
            "string",
            "fixtures/inputs/execution_date_saturday.txt",
            "backup_database",
            media_type="text/plain",
        ),
        artifact(
            "backup_strategy_decision",
            "Backup strategy decision",
            "decision",
            producer="date_check_task",
            role="decision",
            schema_ref="contracts/artifacts/backup_strategy_decision.schema.json",
        ),
        external_artifact(
            "database_resource",
            "Database resource",
            "object",
            "fixtures/inputs/database_resource.json",
            "backup_database",
            sensitivity="confidential",
        ),
        artifact(
            "backup_file",
            "Selected backup file",
            "binary",
            producer=["full_backup_task", "incremental_backup_task"],
            media_type="application/octet-stream",
            sensitivity="confidential",
        ),
        artifact(
            "backup_manifest",
            "Selected backup manifest",
            "object",
            producer=["full_backup_task", "incremental_backup_task"],
            schema_ref="contracts/artifacts/backup_manifest.schema.json",
        ),
        artifact(
            "backup_status",
            "Selected backup status",
            "status",
            producer=["full_backup_task", "incremental_backup_task"],
            role="status",
            schema_ref="contracts/artifacts/backup_status.schema.json",
        ),
        artifact(
            "verification_result",
            "Backup verification decision",
            "decision",
            producer="verify_backup_task",
            role="decision",
            schema_ref="contracts/artifacts/verification_result.schema.json",
        ),
        artifact(
            "verification_status",
            "Backup verification status",
            "status",
            producer="verify_backup_task",
            role="status",
            schema_ref="contracts/artifacts/verification_status.schema.json",
        ),
    ]
    sf["bindings"] = [
        binding(
            "date_check_task",
            "execution_date_backup_strategy_decider",
            [("execution_date", "execution_date")],
            [("backup_strategy_decision", "backup_strategy_decision")],
            {
                "full_backup_days": [5],
                "weekday_numbering": "python_monday_0",
                "full_strategy_label": "full",
                "incremental_strategy_label": "incremental",
                "timezone": "UTC",
            },
            "Binds the source Saturday-vs-weekday rule to the reviewed strategy decider.",
        ),
        *[
            binding(
                intent_id,
                "database_backup_artifact_creator",
                [("source_database", "database_resource")],
                [
                    ("backup_file", "backup_file"),
                    ("backup_manifest", "backup_manifest"),
                    ("backup_status", "backup_status"),
                ],
                {
                    "backup_mode": mode,
                    "database_engine": "postgresql",
                    "backup_profile": "pg_dump_custom",
                    "backup_scope": {"whole_database": True},
                    "output_path": "/workspace/artifacts/backup_file.dump",
                    "overwrite_output": True,
                },
                f"Executes the reviewed {mode} backup contract for the selected branch.",
            )
            for intent_id, mode in (("full_backup_task", "full"), ("incremental_backup_task", "incremental"))
        ],
        binding(
            "verify_backup_task",
            "backup_artifact_integrity_verifier",
            [("backup_file", "backup_file"), ("backup_manifest", "backup_manifest")],
            [
                ("verification_result", "verification_result"),
                ("verification_status", "verification_status"),
            ],
            {"require_non_empty": True, "require_checksum_match": True},
            "Verifies the logical conditional backup artifact emitted by the selected branch.",
        ),
    ]
    sf["policies"]["service_overrides"] = [
        {
            "intent_id": intent_id,
            "retries": 2,
            "retry_delay_seconds": 300,
            "timeout_seconds": 3600,
            "network_access": "required",
        }
        for intent_id in ("full_backup_task", "incremental_backup_task")
    ] + [
        {
            "intent_id": "verify_backup_task",
            "retries": 2,
            "retry_delay_seconds": 300,
            "timeout_seconds": 600,
            "network_access": "forbidden",
        }
    ]
    sf["validation_expectations"] = validation_expectations(
        "Schemas, provenance files, and pinned catalogue checksum validate.",
        "Every source step is explicitly service- or orchestration-accounted.",
        "The three active catalogue bindings resolve from the 0.1.0 snapshot.",
        "Conditional backup outputs, parameters, and policies close against contracts.",
        "The branch/merge Argo DAG and CronWorkflow compile deterministically.",
        "Saturday and weekday backup scenarios execute with one selected branch each.",
        "Strategy, backup mode, checksum verification, and branch exclusivity assertions hold.",
    )
    add_source_accounting(sf, {"start_backup_process", "backup_complete"})
    rebuild_consumers(sf)
    write_yaml(instance / "gold" / "serviceflow.yaml", sf)

    write_yaml(
        instance / "runtime" / "manifest.yaml",
        {
            "runtime_manifest_version": "0.1.0",
            "pipeline_id": "backup_strategy_selector",
            "image": "python:3.12-slim",
            "workflow_parameters": [{"name": "exec-date-fixture", "default": "execution_date_saturday.txt"}],
            "tasks": [
                {
                    "intent_id": "date_check_task",
                    "script": "scripts/02_date_check_task.py",
                    "arguments": [
                        "--workspace",
                        "{workspace}",
                        "--execution-date",
                        "{fixtures}/{exec-date-fixture}",
                    ],
                    "output_parameters": [
                        {"name": "strategy", "path": "/workspace/artifacts/backup_strategy.txt"}
                    ],
                    "retries": 2,
                },
                {
                    "intent_id": "full_backup_task",
                    "script": "scripts/01_create_backup.py",
                    "dependencies": ["date_check_task"],
                    "when": "{{tasks.date_check_task.outputs.parameters.strategy}} == full",
                    "local_condition": {
                        "path": "artifacts/backup_strategy_decision.json",
                        "json_path": "selected_strategy",
                        "equals": "full",
                    },
                    "arguments": [
                        "--workspace",
                        "{workspace}",
                        "--database-resource",
                        "{fixtures}/database_resource.json",
                        "--mode",
                        "full",
                    ],
                    "retries": 2,
                },
                {
                    "intent_id": "incremental_backup_task",
                    "script": "scripts/01_create_backup.py",
                    "dependencies": ["date_check_task"],
                    "when": "{{tasks.date_check_task.outputs.parameters.strategy}} == incremental",
                    "local_condition": {
                        "path": "artifacts/backup_strategy_decision.json",
                        "json_path": "selected_strategy",
                        "equals": "incremental",
                    },
                    "arguments": [
                        "--workspace",
                        "{workspace}",
                        "--database-resource",
                        "{fixtures}/database_resource.json",
                        "--mode",
                        "incremental",
                    ],
                    "retries": 2,
                },
                {
                    "intent_id": "verify_backup_task",
                    "script": "scripts/02_verify_backup.py",
                    "depends": "(full_backup_task.Succeeded || incremental_backup_task.Succeeded)",
                    "arguments": ["--workspace", "{workspace}"],
                    "retries": 2,
                },
            ],
            "scenarios": [
                {"name": "saturday_full_backup", "parameters": {"exec-date-fixture": "execution_date_saturday.txt"}},
                {"name": "weekday_incremental_backup", "parameters": {"exec-date-fixture": "execution_date_weekday.txt"}},
            ],
            "cron": {"schedule": "0 0 * * *", "timezone": "UTC"},
        },
    )
    write_yaml(
        instance / "gold" / "assertions.yaml",
        {
            "assertions_version": "0.1.0",
            "pipeline_id": "backup_strategy_selector",
            "scenarios": [
                {
                    "scenario": "saturday_full_backup",
                    "assertions": [
                        {
                            "assertion_id": "full_strategy_selected",
                            "type": "json_path_equals",
                            "path": "artifacts/backup_strategy_decision.json",
                            "json_path": "selected_strategy",
                            "expected": "full",
                        },
                        {
                            "assertion_id": "full_backup_executed",
                            "type": "json_path_equals",
                            "path": "artifacts/backup_status.json",
                            "json_path": "backup_mode",
                            "expected": "full",
                        },
                        {
                            "assertion_id": "full_backup_verified",
                            "type": "json_path_equals",
                            "path": "artifacts/verification_result.json",
                            "json_path": "valid",
                            "expected": True,
                        },
                    ],
                },
                {
                    "scenario": "weekday_incremental_backup",
                    "assertions": [
                        {
                            "assertion_id": "incremental_strategy_selected",
                            "type": "json_path_equals",
                            "path": "artifacts/backup_strategy_decision.json",
                            "json_path": "selected_strategy",
                            "expected": "incremental",
                        },
                        {
                            "assertion_id": "incremental_backup_executed",
                            "type": "json_path_equals",
                            "path": "artifacts/backup_status.json",
                            "json_path": "backup_mode",
                            "expected": "incremental",
                        },
                        {
                            "assertion_id": "incremental_backup_verified",
                            "type": "json_path_equals",
                            "path": "artifacts/verification_result.json",
                            "json_path": "valid",
                            "expected": True,
                        },
                    ],
                },
            ],
        },
    )
    write_text(
        instance / "runtime" / "scripts" / "01_create_backup.py",
        '''
        #!/usr/bin/env python3
        """Create the branch-selected mock database backup artifact."""

        from __future__ import annotations

        import argparse
        import hashlib
        import json
        from pathlib import Path


        def main() -> None:
            parser = argparse.ArgumentParser()
            parser.add_argument("--workspace", type=Path, required=True)
            parser.add_argument("--database-resource", type=Path, required=True)
            parser.add_argument("--mode", choices=("full", "incremental"), required=True)
            args = parser.parse_args()

            artifacts = args.workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            database = json.loads(args.database_resource.read_text(encoding="utf-8"))
            payload = f"mock-{args.mode}-backup:{database.get('database', 'backup_target_db')}\\n".encode()
            payload *= 32
            backup_path = artifacts / "backup_file.dump"
            backup_path.write_bytes(payload)
            checksum = hashlib.sha256(payload).hexdigest()
            manifest = {
                "backup_mode": args.mode,
                "database_engine": database.get("engine", "postgresql"),
                "output_uri": str(backup_path),
                "artifact_created": True,
                "checksum_sha256": checksum,
                "size_bytes": len(payload),
                "checkpoint_reference": "mock-checkpoint-2024-01-07" if args.mode == "incremental" else None,
            }
            (artifacts / "backup_manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\\n", encoding="utf-8"
            )
            status = {
                "success": True,
                "backup_mode": args.mode,
                "backup_attempted": True,
                "output_uri": str(backup_path),
                "bytes_written": len(payload),
                "errors": [],
            }
            (artifacts / "backup_status.json").write_text(
                json.dumps(status, indent=2) + "\\n", encoding="utf-8"
            )


        if __name__ == "__main__":
            main()
        ''',
    )
    write_text(
        instance / "runtime" / "scripts" / "02_verify_backup.py",
        '''
        #!/usr/bin/env python3
        """Verify the branch-selected mock database backup artifact."""

        from __future__ import annotations

        import argparse
        import hashlib
        import json
        from pathlib import Path


        def main() -> None:
            parser = argparse.ArgumentParser()
            parser.add_argument("--workspace", type=Path, required=True)
            args = parser.parse_args()

            artifacts = args.workspace / "artifacts"
            backup_path = artifacts / "backup_file.dump"
            manifest = json.loads((artifacts / "backup_manifest.json").read_text(encoding="utf-8"))
            payload = backup_path.read_bytes()
            checksum_matched = hashlib.sha256(payload).hexdigest() == manifest["checksum_sha256"]
            valid = bool(payload) and checksum_matched
            result = {
                "valid": valid,
                "checks_run": 3,
                "checks_failed": 0 if valid else 1,
                "artifact_readable": True,
                "checksum_matched": checksum_matched,
                "completeness_passed": bool(payload),
                "errors": [] if valid else ["backup integrity check failed"],
            }
            (artifacts / "verification_result.json").write_text(
                json.dumps(result, indent=2) + "\\n", encoding="utf-8"
            )
            (artifacts / "verification_status.json").write_text(
                json.dumps(
                    {
                        "success": valid,
                        "verification_attempted": True,
                        "valid": valid,
                        "profile": "checksum_and_non_empty",
                        "errors": result["errors"],
                    },
                    indent=2,
                )
                + "\\n",
                encoding="utf-8",
            )


        if __name__ == "__main__":
            main()
        ''',
    )


def harden_fraud_triage() -> None:
    instance = INSTANCES / "fraud_detection_triage"
    sf = load_yaml(instance / "gold" / "serviceflow.yaml")
    add_source_accounting(sf)
    sf["validation_expectations"] = validation_expectations(
        "Schemas, files, and provenance checks validate.",
        "All five source steps have explicit service accounting.",
        "Five reviewed fraud and notification bindings resolve.",
        "Risk, branch-status, notification, and policy contracts close.",
        "The risk branch/merge Argo DAG and CronWorkflow compile.",
        "High-risk and low-risk scenarios execute one route each.",
        "Risk threshold, selected route, route exclusivity, and notification assertions hold.",
    )
    rebuild_consumers(sf)
    write_yaml(instance / "gold" / "serviceflow.yaml", sf)


def harden_file_arrival() -> None:
    instance = INSTANCES / "file_arrival_watcher"
    sf = load_yaml(instance / "gold" / "serviceflow.yaml")
    sf["external_systems"] = [
        {
            "system_id": "incoming_filesystem",
            "type": "filesystem",
            "name": "Incoming transaction directory",
            "identifier": "/data/incoming",
            "access_mode": "read",
            "authentication": "none",
            "mock_strategy": "fixture",
        },
        {
            "system_id": "postgres_database",
            "type": "database",
            "name": "PostgreSQL transactions database",
            "identifier": "localhost:5432/public.transactions",
            "access_mode": "write",
            "authentication": "secret",
            "mock_strategy": "fixture",
        },
    ]
    configure_intent(
        sf,
        "wait_for_file",
        capability="Observe whether the expected dated transaction CSV is available before the timeout.",
        inputs=["file_location_resource"],
        outputs=["availability_decision", "check_status"],
        external_system_refs=["incoming_filesystem"],
        network_access="optional",
        secret_access="forbidden",
        rationale="The source is a file-arrival sensor with explicit poke and timeout semantics.",
        category="Sensor",
    )
    configure_intent(
        sf,
        "validate_schema",
        capability="Validate the arrived transaction CSV schema and materialize a reviewed tabular representation.",
        inputs=["transaction_csv"],
        outputs=["validated_dataset", "validated_data_object", "validation_status"],
        external_system_refs=[],
        network_access="forbidden",
        secret_access="forbidden",
        rationale="The source validates the arriving CSV before database loading.",
        category="QualityCheck",
    )
    configure_intent(
        sf,
        "load_db",
        capability="Load the schema-validated transaction CSV into the target PostgreSQL table.",
        inputs=["transaction_csv", "postgres_resource"],
        outputs=["target_db_reference", "load_status"],
        external_system_refs=["postgres_database"],
        network_access="required",
        secret_access="required",
        rationale="The source writes the same file only after the preceding schema-validation gate passes.",
        category="Loader",
    )
    sf["artifacts"] = [
        external_artifact(
            "file_location_resource",
            "Incoming file location",
            "object",
            "fixtures/inputs/file_location.json",
            "incoming_filesystem",
        ),
        artifact(
            "availability_decision",
            "File availability decision",
            "decision",
            producer="wait_for_file",
            role="decision",
            schema_ref="contracts/artifacts/availability_decision.schema.json",
        ),
        artifact(
            "check_status",
            "File sensor status",
            "status",
            producer="wait_for_file",
            role="status",
            schema_ref="contracts/artifacts/check_status.schema.json",
        ),
        external_artifact(
            "transaction_csv",
            "Incoming transaction CSV",
            "csv",
            "fixtures/inputs/transactions_20240115.csv",
            "incoming_filesystem",
            media_type="text/csv",
            sensitivity="confidential",
        ),
        artifact(
            "validated_dataset",
            "Validated transaction dataset",
            "table",
            producer="validate_schema",
            schema_ref="contracts/artifacts/validated_dataset.schema.json",
            sensitivity="confidential",
        ),
        artifact(
            "validated_data_object",
            "Validated transaction data object",
            "object",
            producer="validate_schema",
            schema_ref="contracts/artifacts/validated_data_object.schema.json",
            sensitivity="confidential",
        ),
        artifact(
            "validation_status",
            "Schema validation status",
            "status",
            producer="validate_schema",
            role="status",
            schema_ref="contracts/artifacts/validation_status.schema.json",
        ),
        external_artifact(
            "postgres_resource",
            "PostgreSQL target resource",
            "object",
            "fixtures/inputs/postgres_resource.json",
            "postgres_database",
            sensitivity="confidential",
        ),
        artifact(
            "target_db_reference",
            "Target database reference",
            "object",
            producer="load_db",
            schema_ref="contracts/artifacts/target_db_reference.schema.json",
        ),
        artifact(
            "load_status",
            "Database load status",
            "status",
            producer="load_db",
            role="status",
            schema_ref="contracts/artifacts/load_status.schema.json",
        ),
    ]
    sf["bindings"] = [
        binding(
            "wait_for_file",
            "file_location_availability_sensor",
            [("file_location_resource", "file_location_resource")],
            [("availability_decision", "availability_decision"), ("check_status", "check_status")],
            {
                "location_type": "filesystem",
                "path": "/data/incoming/transactions_{{ ds_nodash }}.csv",
                "availability_condition": "exists",
                "filename_pattern": "transactions_*.csv",
            },
            "Binds the source file sensor, including its dated incoming-file contract.",
        ),
        binding(
            "validate_schema",
            "csv_tabular_schema_validating_loader",
            [("csv_file", "transaction_csv")],
            [
                ("validated_dataset", "validated_dataset"),
                ("validated_data_object", "validated_data_object"),
                ("validation_status", "validation_status"),
            ],
            {
                "required_columns": [
                    "transaction_id",
                    "customer_id",
                    "amount",
                    "currency",
                    "transaction_date",
                ],
                "has_header": True,
                "fail_on_empty": True,
                "output_path": "/workspace/artifacts/validated_data_object.json",
            },
            "Validates the source transaction CSV before it is eligible for loading.",
        ),
        binding(
            "load_db",
            "database_csv_snapshot_importer",
            [("csv_snapshot", "transaction_csv"), ("target_database", "postgres_resource")],
            [("target_database_reference", "target_db_reference"), ("load_status", "load_status")],
            {
                "import_spec": {"table": "public.transactions"},
                "load_mode": "upsert",
                "has_header": True,
                "target_label": "public.transactions",
            },
            "Loads the same incoming CSV only after the schema-validation task succeeds.",
        ),
    ]
    sf["policies"]["service_overrides"] = [
        {"intent_id": "wait_for_file", "retries": 2, "timeout_seconds": 86400, "network_access": "optional"},
        {"intent_id": "validate_schema", "retries": 2, "timeout_seconds": 180, "network_access": "forbidden"},
        {"intent_id": "load_db", "retries": 2, "timeout_seconds": 600, "network_access": "required"},
    ]
    sf["validation_expectations"] = validation_expectations(
        "Schemas, files, and provenance checks validate.",
        "All three source steps have explicit service accounting.",
        "Sensor, CSV validation, and database importer bindings resolve.",
        "Sensor, validation, load, and database-resource contracts close.",
        "The sensor-gated Argo DAG and CronWorkflow compile.",
        "Arrival and missing-file scenarios execute without invoking invalid downstream work.",
        "Availability, route exclusion, validation, and loaded-row assertions hold.",
    )
    add_source_accounting(sf)
    rebuild_consumers(sf)
    write_yaml(instance / "gold" / "serviceflow.yaml", sf)
    write_yaml(
        instance / "runtime" / "manifest.yaml",
        {
            "runtime_manifest_version": "0.1.0",
            "pipeline_id": "file_arrival_watcher",
            "image": "python:3.12-slim",
            "workflow_parameters": [{"name": "fixture-file", "default": "transactions_20240115.csv"}],
            "tasks": [
                {
                    "intent_id": "wait_for_file",
                    "script": "scripts/01_wait_for_file.py",
                    "arguments": [
                        "--workspace",
                        "{workspace}",
                        "--file-location",
                        "{fixtures}/file_location.json",
                        "--fixture",
                        "{fixtures}/{fixture-file}",
                    ],
                    "output_parameters": [
                        {"name": "available", "path": "/workspace/artifacts/availability.txt"}
                    ],
                    "retries": 2,
                },
                {
                    "intent_id": "validate_schema",
                    "script": "scripts/02_validate_schema.py",
                    "dependencies": ["wait_for_file"],
                    "when": "{{tasks.wait_for_file.outputs.parameters.available}} == true",
                    "local_condition": {
                        "path": "artifacts/availability_decision.json",
                        "json_path": "available",
                        "equals": True,
                    },
                    "arguments": ["--workspace", "{workspace}", "--fixture", "{fixtures}/{fixture-file}"],
                    "retries": 2,
                },
                {
                    "intent_id": "load_db",
                    "script": "scripts/03_load_db.py",
                    "dependencies": ["validate_schema"],
                    "when": "{{tasks.wait_for_file.outputs.parameters.available}} == true",
                    "local_condition": {
                        "path": "artifacts/availability_decision.json",
                        "json_path": "available",
                        "equals": True,
                    },
                    "arguments": [
                        "--workspace",
                        "{workspace}",
                        "--database-resource",
                        "{fixtures}/postgres_resource.json",
                    ],
                    "retries": 2,
                },
            ],
            "scenarios": [
                {"name": "file_arrives", "parameters": {"fixture-file": "transactions_20240115.csv"}},
                {"name": "file_missing", "parameters": {"fixture-file": "transactions_missing.csv"}},
            ],
            "cron": {"schedule": "0 0 * * *", "timezone": "UTC"},
        },
    )
    write_yaml(
        instance / "gold" / "assertions.yaml",
        {
            "assertions_version": "0.1.0",
            "pipeline_id": "file_arrival_watcher",
            "scenarios": [
                {
                    "scenario": "file_arrives",
                    "assertions": [
                        {"assertion_id": "file_available", "type": "json_path_equals", "path": "artifacts/availability_decision.json", "json_path": "available", "expected": True},
                        {"assertion_id": "validation_succeeds", "type": "json_path_equals", "path": "artifacts/validation_status.json", "json_path": "success", "expected": True},
                        {"assertion_id": "rows_loaded", "type": "json_path_equals", "path": "artifacts/load_status.json", "json_path": "rows_loaded", "expected": 3},
                    ],
                },
                {
                    "scenario": "file_missing",
                    "assertions": [
                        {"assertion_id": "missing_file_observed", "type": "json_path_equals", "path": "artifacts/availability_decision.json", "json_path": "available", "expected": False},
                        {"assertion_id": "validation_not_invoked", "type": "file_absent", "path": "artifacts/validation_status.json"},
                        {"assertion_id": "load_not_invoked", "type": "file_absent", "path": "artifacts/load_status.json"},
                    ],
                },
            ],
        },
    )
    write_text(
        instance / "runtime" / "scripts" / "01_wait_for_file.py",
        '''
        #!/usr/bin/env python3
        """Observe a mock dated input file without sleeping through the timeout."""

        from __future__ import annotations

        import argparse
        import json
        from pathlib import Path


        def main() -> None:
            parser = argparse.ArgumentParser()
            parser.add_argument("--workspace", type=Path, required=True)
            parser.add_argument("--file-location", type=Path, required=True)
            parser.add_argument("--fixture", type=Path, required=True)
            args = parser.parse_args()
            artifacts = args.workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            location = json.loads(args.file_location.read_text(encoding="utf-8"))
            available = args.fixture.is_file()
            decision = {
                "available": available,
                "path": str(args.fixture),
                "configured_location": location["path"],
                "reason": "fixture_present" if available else "fixture_missing_before_timeout",
            }
            (artifacts / "availability_decision.json").write_text(
                json.dumps(decision, indent=2) + "\\n", encoding="utf-8"
            )
            (artifacts / "availability.txt").write_text("true" if available else "false", encoding="utf-8")
            status = {"success": True, "available": available, "errors": []}
            (artifacts / "check_status.json").write_text(
                json.dumps(status, indent=2) + "\\n", encoding="utf-8"
            )


        if __name__ == "__main__":
            main()
        ''',
    )
    write_text(
        instance / "runtime" / "scripts" / "02_validate_schema.py",
        '''
        #!/usr/bin/env python3
        """Validate and materialize the arrived transaction CSV."""

        from __future__ import annotations

        import argparse
        import csv
        import json
        import shutil
        from pathlib import Path


        REQUIRED_COLUMNS = ["transaction_id", "customer_id", "amount", "currency", "transaction_date"]


        def main() -> None:
            parser = argparse.ArgumentParser()
            parser.add_argument("--workspace", type=Path, required=True)
            parser.add_argument("--fixture", type=Path, required=True)
            args = parser.parse_args()
            artifacts = args.workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            destination = artifacts / "transactions.csv"
            shutil.copyfile(args.fixture, destination)
            with destination.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                columns = reader.fieldnames or []
            missing = [column for column in REQUIRED_COLUMNS if column not in columns]
            if missing:
                raise SystemExit(f"missing required columns: {missing}")
            dataset = {"columns": columns, "rows": rows}
            (artifacts / "validated_dataset.json").write_text(
                json.dumps(dataset, indent=2) + "\\n", encoding="utf-8"
            )
            data_object = {"source_uri": str(destination), "record_count": len(rows), "columns": columns}
            (artifacts / "validated_data_object.json").write_text(
                json.dumps(data_object, indent=2) + "\\n", encoding="utf-8"
            )
            status = {"success": True, "rows_read": len(rows), "errors": []}
            (artifacts / "validation_status.json").write_text(
                json.dumps(status, indent=2) + "\\n", encoding="utf-8"
            )


        if __name__ == "__main__":
            main()
        ''',
    )
    write_text(
        instance / "runtime" / "scripts" / "03_load_db.py",
        '''
        #!/usr/bin/env python3
        """Load the schema-validated transaction CSV into a local database mock."""

        from __future__ import annotations

        import argparse
        import csv
        import json
        from pathlib import Path


        def main() -> None:
            parser = argparse.ArgumentParser()
            parser.add_argument("--workspace", type=Path, required=True)
            parser.add_argument("--database-resource", type=Path, required=True)
            args = parser.parse_args()
            artifacts = args.workspace / "artifacts"
            with (artifacts / "transactions.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            resource = json.loads(args.database_resource.read_text(encoding="utf-8"))
            database = args.workspace / "mock_postgres"
            database.mkdir(parents=True, exist_ok=True)
            (database / "transactions.json").write_text(json.dumps(rows, indent=2) + "\\n", encoding="utf-8")
            reference = {"target_table": "public.transactions", "rows_imported": len(rows), "driver": resource["driver"]}
            (artifacts / "target_db_reference.json").write_text(
                json.dumps(reference, indent=2) + "\\n", encoding="utf-8"
            )
            status = {"success": True, "rows_loaded": len(rows), "errors": []}
            (artifacts / "load_status.json").write_text(
                json.dumps(status, indent=2) + "\\n", encoding="utf-8"
            )


        if __name__ == "__main__":
            main()
        ''',
    )


def harden_database_replication() -> None:
    instance = INSTANCES / "database_replication_fanout"
    sf = load_yaml(instance / "gold" / "serviceflow.yaml")
    sf["external_systems"] = [
        {
            "system_id": "production_database",
            "type": "database",
            "name": "Production database",
            "identifier": "production",
            "access_mode": "read",
            "authentication": "secret",
            "mock_strategy": "fixture",
        },
        *[
            {
                "system_id": f"{environment}_database",
                "type": "database",
                "name": f"{environment.title()} database",
                "identifier": environment,
                "access_mode": "write",
                "authentication": "secret",
                "mock_strategy": "fixture",
            }
            for environment in ("dev", "staging", "qa")
        ],
    ]
    configure_intent(
        sf,
        "dump_prod_csv",
        capability="Export the production database snapshot as a deterministic CSV artifact.",
        inputs=["prod_db_resource"],
        outputs=["csv_snapshot", "export_status"],
        external_system_refs=["production_database"],
        network_access="required",
        secret_access="required",
        rationale="The source explicitly exports production data before the fan-out copies.",
        category="Extractor",
    )
    for environment in ("dev", "staging", "qa"):
        configure_intent(
            sf,
            f"copy_{environment}",
            capability=f"Replace the {environment} database table from the production CSV snapshot.",
            inputs=["csv_snapshot", f"{environment}_db_resource"],
            outputs=[f"{environment}_ref", f"{environment}_load_status"],
            external_system_refs=[f"{environment}_database"],
            network_access="required",
            secret_access="required",
            rationale="The source executes this database import as one branch of the copy fan-out.",
            category="Loader",
        )
    sf["artifacts"] = [
        external_artifact(
            "prod_db_resource",
            "Production database resource",
            "object",
            "fixtures/inputs/prod_db.json",
            "production_database",
            sensitivity="confidential",
        ),
        artifact(
            "csv_snapshot",
            "Production CSV snapshot",
            "csv",
            producer="dump_prod_csv",
            media_type="text/csv",
            sensitivity="confidential",
        ),
        artifact(
            "export_status",
            "Snapshot export status",
            "status",
            producer="dump_prod_csv",
            role="status",
            schema_ref="contracts/artifacts/st.schema.json",
        ),
    ]
    for environment in ("dev", "staging", "qa"):
        sf["artifacts"].extend(
            [
                external_artifact(
                    f"{environment}_db_resource",
                    f"{environment.title()} database resource",
                    "object",
                    f"fixtures/inputs/{environment}_db.json",
                    f"{environment}_database",
                    sensitivity="confidential",
                ),
                artifact(
                    f"{environment}_ref",
                    f"{environment.title()} database reference",
                    "object",
                    producer=f"copy_{environment}",
                    schema_ref="contracts/artifacts/database_reference.schema.json",
                ),
                artifact(
                    f"{environment}_load_status",
                    f"{environment.title()} import status",
                    "status",
                    producer=f"copy_{environment}",
                    role="status",
                    schema_ref="contracts/artifacts/st.schema.json",
                ),
            ]
        )
    sf["bindings"] = [
        binding(
            "dump_prod_csv",
            "database_csv_snapshot_exporter",
            [("source_database", "prod_db_resource")],
            [("csv_snapshot", "csv_snapshot"), ("export_status", "export_status")],
            {
                "export_spec": {"table": "data", "query": "SELECT * FROM data"},
                "output_path": "/workspace/artifacts/snapshot.csv",
                "include_header": True,
                "overwrite_output": True,
            },
            "Exports the production source table once before parallel imports.",
        ),
        *[
            binding(
                f"copy_{environment}",
                "database_csv_snapshot_importer",
                [("csv_snapshot", "csv_snapshot"), ("target_database", f"{environment}_db_resource")],
                [
                    ("target_database_reference", f"{environment}_ref"),
                    ("load_status", f"{environment}_load_status"),
                ],
                {
                    "import_spec": {"table": "data"},
                    "load_mode": "replace",
                    "target_label": environment,
                    "has_header": True,
                },
                f"Imports the shared production snapshot into the {environment} database branch.",
            )
            for environment in ("dev", "staging", "qa")
        ],
    ]
    sf["policies"]["default_retries"] = 2
    sf["policies"]["default_retry_delay_seconds"] = 300
    sf["policies"]["service_overrides"] = [
        {
            "intent_id": intent_id,
            "retries": 2,
            "retry_delay_seconds": 300,
            "timeout_seconds": 600,
            "network_access": "required",
        }
        for intent_id in ("dump_prod_csv", "copy_dev", "copy_staging", "copy_qa")
    ]
    sf["policies"]["governance"]["network_default"] = "required"
    sf["validation_expectations"] = validation_expectations(
        "Schemas, files, and provenance checks validate.",
        "All four source steps have explicit service accounting.",
        "The export and shared importer catalogue bindings resolve.",
        "Database resources, CSV snapshot, import parameters, and policies close.",
        "The production-export and three-way fan-out Argo DAG compiles.",
        "The bounded production snapshot and all target imports execute.",
        "Snapshot row count and every target row-count/reference assertion hold.",
    )
    add_source_accounting(sf)
    rebuild_consumers(sf)
    write_yaml(instance / "gold" / "serviceflow.yaml", sf)
    write_yaml(
        instance / "runtime" / "manifest.yaml",
        {
            "runtime_manifest_version": "0.1.0",
            "pipeline_id": "database_replication_fanout",
            "image": "python:3.12-slim",
            "workflow_parameters": [],
            "tasks": [
                {
                    "intent_id": "dump_prod_csv",
                    "script": "scripts/01_run.py",
                    "arguments": [
                        "--workspace",
                        "{workspace}",
                        "--step",
                        "export",
                        "--database-resource",
                        "{fixtures}/prod_db.json",
                        "--source-fixture",
                        "{fixtures}/prod_snapshot.csv",
                    ],
                    "retries": 2,
                },
                *[
                    {
                        "intent_id": f"copy_{environment}",
                        "script": "scripts/01_run.py",
                        "dependencies": ["dump_prod_csv"],
                        "arguments": [
                            "--workspace",
                            "{workspace}",
                            "--step",
                            "import",
                            "--target-label",
                            environment,
                            "--database-resource",
                            f"{{fixtures}}/{environment}_db.json",
                        ],
                        "retries": 2,
                    }
                    for environment in ("dev", "staging", "qa")
                ],
            ],
            "scenarios": [{"name": "replication", "parameters": {}}],
        },
    )
    write_yaml(
        instance / "gold" / "assertions.yaml",
        {
            "assertions_version": "0.1.0",
            "pipeline_id": "database_replication_fanout",
            "scenarios": [
                {
                    "scenario": "replication",
                    "assertions": [
                        {"assertion_id": "three_snapshot_rows", "type": "csv_row_count", "path": "artifacts/snapshot.csv", "expected": 3},
                        {"assertion_id": "exported_rows", "type": "json_path_equals", "path": "artifacts/export_status.json", "json_path": "rows_exported", "expected": 3},
                        *[
                            {"assertion_id": f"{environment}_rows_loaded", "type": "json_path_equals", "path": f"artifacts/{environment}_load_status.json", "json_path": "rows_loaded", "expected": 3}
                            for environment in ("dev", "staging", "qa")
                        ],
                    ],
                }
            ],
        },
    )
    write_text(
        instance / "fixtures" / "inputs" / "prod_snapshot.csv",
        "id,name,amount\n1,alpha,100\n2,beta,200\n3,gamma,300\n",
    )
    write_json(
        instance / "fixtures" / "inputs" / "prod_db.json",
        {"driver": "filesystem-mock", "engine": "postgresql", "target": "production", "table": "data"},
    )
    for environment in ("dev", "staging", "qa"):
        write_json(
            instance / "fixtures" / "inputs" / f"{environment}_db.json",
            {"driver": "filesystem-mock", "engine": "postgresql", "target": environment, "table": "data"},
        )
    write_json(instance / "contracts" / "artifacts" / "st.schema.json", status_schema())
    write_json(
        instance / "contracts" / "artifacts" / "database_reference.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["target", "table", "rows_imported"],
            "properties": {
                "target": {"type": "string", "minLength": 1},
                "table": {"type": "string", "minLength": 1},
                "rows_imported": {"type": "integer", "minimum": 0},
            },
        },
    )
    write_text(
        instance / "runtime" / "scripts" / "01_run.py",
        '''
        #!/usr/bin/env python3
        """Run deterministic production export and target import mocks."""

        from __future__ import annotations

        import argparse
        import csv
        import json
        import shutil
        from pathlib import Path


        def main() -> None:
            parser = argparse.ArgumentParser()
            parser.add_argument("--workspace", type=Path, required=True)
            parser.add_argument("--step", choices=("export", "import"), required=True)
            parser.add_argument("--database-resource", type=Path, required=True)
            parser.add_argument("--source-fixture", type=Path)
            parser.add_argument("--target-label")
            args = parser.parse_args()
            artifacts = args.workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            database = json.loads(args.database_resource.read_text(encoding="utf-8"))
            if args.step == "export":
                if args.source_fixture is None:
                    raise SystemExit("--source-fixture is required for export")
                snapshot = artifacts / "snapshot.csv"
                shutil.copyfile(args.source_fixture, snapshot)
                with snapshot.open(encoding="utf-8", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                status = {"success": True, "source_database": database["target"], "rows_exported": len(rows), "errors": []}
                (artifacts / "export_status.json").write_text(json.dumps(status, indent=2) + "\\n", encoding="utf-8")
                return
            if args.target_label is None:
                raise SystemExit("--target-label is required for import")
            with (artifacts / "snapshot.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            target = args.workspace / "mock_databases"
            target.mkdir(parents=True, exist_ok=True)
            (target / f"{args.target_label}.json").write_text(json.dumps(rows, indent=2) + "\\n", encoding="utf-8")
            reference = {"target": database["target"], "table": database["table"], "rows_imported": len(rows)}
            (artifacts / f"{args.target_label}_ref.json").write_text(json.dumps(reference, indent=2) + "\\n", encoding="utf-8")
            status = {"success": True, "target": args.target_label, "rows_loaded": len(rows), "errors": []}
            (artifacts / f"{args.target_label}_load_status.json").write_text(json.dumps(status, indent=2) + "\\n", encoding="utf-8")


        if __name__ == "__main__":
            main()
        ''',
    )


def harden_multi_region() -> None:
    instance = INSTANCES / "multi_region_ecommerce_analytics"
    sf = load_yaml(instance / "gold" / "serviceflow.yaml")
    remove_intents(sf, {"start_pipeline", "end_pipeline"})
    regions = [
        ("us_east", "US-East", "us_east"),
        ("us_west", "US-West", "us_west"),
        ("eu", "EU", "eu"),
        ("apac", "APAC", "apac"),
    ]
    sf["external_systems"] = [
        {
            "system_id": "regional_sales_databases",
            "type": "database",
            "name": "Regional sales databases",
            "identifier": "regional_sales",
            "access_mode": "read",
            "authentication": "secret",
            "mock_strategy": "fixture",
        }
    ]
    for slug, label, _ in regions:
        configure_intent(
            sf,
            f"ingest_{slug}",
            capability=f"Export the {label} regional sales database as a CSV snapshot.",
            inputs=[f"{slug}_database_resource"],
            outputs=[f"{slug}_sales_csv", f"{slug}_ingest_status"],
            external_system_refs=["regional_sales_databases"],
            network_access="required",
            secret_access="required",
            rationale="The source ingests this region from a database before currency conversion.",
            category="Extractor",
        )
        configure_intent(
            sf,
            f"convert_currency_{slug}",
            capability=f"Convert {label} sales revenue to USD using the reviewed exchange-rate table.",
            inputs=[f"{slug}_sales_csv", "exchange_rates"],
            outputs=[f"{slug}_usd_dataset", f"{slug}_convert_status"],
            external_system_refs=[],
            network_access="forbidden",
            secret_access="forbidden",
            rationale="The source applies a region-specific currency conversion after ingestion.",
            category="Transformer",
        )
    configure_intent(
        sf,
        "aggregate_global_revenue",
        capability="Aggregate all four USD-converted regional sales files into a global revenue report.",
        inputs=[f"{slug}_usd_dataset" for slug, _, _ in regions],
        outputs=["global_report", "aggregate_status"],
        external_system_refs=[],
        network_access="forbidden",
        secret_access="forbidden",
        rationale="The source explicitly fans in all converted regional files into one report.",
        category="Aggregator",
    )
    sf["control_flow"] = {
        "edges": [
            *[
                {"from": f"ingest_{slug}", "to": f"convert_currency_{slug}"}
                for slug, _, _ in regions
            ],
            *[
                {"from": f"convert_currency_{slug}", "to": "aggregate_global_revenue"}
                for slug, _, _ in regions
            ],
        ],
        "parallel_groups": [
            {"group_id": "ingest_phase", "intent_ids": [f"ingest_{slug}" for slug, _, _ in regions]},
            {"group_id": "convert_phase", "intent_ids": [f"convert_currency_{slug}" for slug, _, _ in regions]},
        ],
        "branches": [],
        "gates": [],
    }
    sf["artifacts"] = []
    for slug, label, _ in regions:
        sf["artifacts"].extend(
            [
                external_artifact(
                    f"{slug}_database_resource",
                    f"{label} sales database resource",
                    "object",
                    f"fixtures/inputs/{slug}_database.json",
                    "regional_sales_databases",
                    sensitivity="confidential",
                ),
                artifact(
                    f"{slug}_sales_csv",
                    f"{label} sales CSV snapshot",
                    "csv",
                    producer=f"ingest_{slug}",
                    media_type="text/csv",
                    sensitivity="confidential",
                ),
                artifact(
                    f"{slug}_ingest_status",
                    f"{label} snapshot export status",
                    "status",
                    producer=f"ingest_{slug}",
                    role="status",
                    schema_ref="contracts/artifacts/st.schema.json",
                ),
            ]
        )
    sf["artifacts"].append(
        external_artifact(
            "exchange_rates",
            "Versioned exchange-rate table",
            "table",
            "fixtures/inputs/exchange_rates.json",
            "regional_sales_databases",
        )
    )
    for slug, label, _ in regions:
        sf["artifacts"].extend(
            [
                artifact(
                    f"{slug}_usd_dataset",
                    f"{label} USD sales CSV",
                    "csv",
                    producer=f"convert_currency_{slug}",
                    media_type="text/csv",
                    sensitivity="confidential",
                ),
                artifact(
                    f"{slug}_convert_status",
                    f"{label} currency-conversion status",
                    "status",
                    producer=f"convert_currency_{slug}",
                    role="status",
                    schema_ref="contracts/artifacts/st.schema.json",
                ),
            ]
        )
    sf["artifacts"].extend(
        [
            artifact(
                "global_report",
                "Global USD revenue report",
                "csv",
                producer="aggregate_global_revenue",
                role="output",
                media_type="text/csv",
                sensitivity="confidential",
                persistence="release",
            ),
            artifact(
                "aggregate_status",
                "Global revenue aggregation status",
                "status",
                producer="aggregate_global_revenue",
                role="status",
                schema_ref="contracts/artifacts/st.schema.json",
                persistence="release",
            ),
        ]
    )
    sf["bindings"] = [
        *[
            binding(
                f"ingest_{slug}",
                "database_csv_snapshot_exporter",
                [("source_database", f"{slug}_database_resource")],
                [("csv_snapshot", f"{slug}_sales_csv"), ("export_status", f"{slug}_ingest_status")],
                {
                    "export_spec": {"table": "sales", "region": label},
                    "output_path": f"/workspace/artifacts/{slug}_sales.csv",
                    "include_header": True,
                    "overwrite_output": True,
                },
                f"Exports the {label} source database as the source-required CSV artifact.",
            )
            for slug, label, _ in regions
        ],
        *[
            binding(
                f"convert_currency_{slug}",
                "regional_sales_currency_usd_converter",
                [("sales_data_file", f"{slug}_sales_csv"), ("exchange_rate_table", "exchange_rates")],
                [
                    ("converted_sales_file", f"{slug}_usd_dataset"),
                    ("conversion_status", f"{slug}_convert_status"),
                ],
                {
                    "region": label,
                    "target_currency": "USD",
                    "amount_columns": ["revenue"],
                    "currency_column": "currency",
                    "missing_rate_policy": "fail",
                    "output_path": f"/workspace/artifacts/{slug}_usd.csv",
                },
                f"Converts the exported {label} CSV with the bound rate table.",
            )
            for slug, label, _ in regions
        ],
        binding(
            "aggregate_global_revenue",
            "multi_region_revenue_report_aggregator",
            [("converted_sales_files", f"{slug}_usd_dataset") for slug, _, _ in regions],
            [("global_revenue_report", "global_report"), ("aggregation_status", "aggregate_status")],
            {
                "report_currency": "USD",
                "revenue_column": "revenue_usd",
                "region_column": "region",
                "grouping_columns": ["region"],
                "output_path_template": "/workspace/artifacts/global_report.csv",
                "include_header": True,
            },
            "Fans in all four converted regional CSVs through the cardinality-many catalogue port.",
        ),
    ]
    sf["policies"]["default_retries"] = 2
    sf["policies"]["default_retry_delay_seconds"] = 300
    sf["policies"]["service_overrides"] = [
        {
            "intent_id": f"ingest_{slug}",
            "retries": 2,
            "retry_delay_seconds": 300,
            "timeout_seconds": 300,
            "network_access": "required",
        }
        for slug, _, _ in regions
    ]
    sf["policies"]["governance"]["allowed_sensitivities"] = ["internal", "confidential"]
    sf["validation_expectations"] = validation_expectations(
        "Schemas, files, and provenance checks validate.",
        "Every source step is explicitly service- or orchestration-accounted.",
        "Database export, currency conversion, and cardinality-many aggregation bindings resolve.",
        "Regional resource, CSV, rate-table, and multi-input aggregation contracts close.",
        "The two-phase fan-out/fan-in Argo DAG compiles.",
        "All four regional exports and conversions execute before aggregation.",
        "Regional USD values, four-input fan-in, and global revenue total assertions hold.",
    )
    add_source_accounting(sf, {"start_pipeline", "end_pipeline"})
    rebuild_consumers(sf)
    write_yaml(instance / "gold" / "serviceflow.yaml", sf)
    write_yaml(
        instance / "runtime" / "manifest.yaml",
        {
            "runtime_manifest_version": "0.1.0",
            "pipeline_id": "multi_region_ecommerce_analytics",
            "image": "python:3.12-slim",
            "workflow_parameters": [],
            "tasks": [
                *[
                    {
                        "intent_id": f"ingest_{slug}",
                        "script": "scripts/01_run.py",
                        "arguments": [
                            "--workspace",
                            "{workspace}",
                            "--step",
                            "export",
                            "--region",
                            slug,
                            "--database-resource",
                            f"{{fixtures}}/{slug}_database.json",
                            "--source-fixture",
                            f"{{fixtures}}/{fixture_name}.csv",
                        ],
                        "retries": 2,
                    }
                    for slug, _, fixture_name in regions
                ],
                *[
                    {
                        "intent_id": f"convert_currency_{slug}",
                        "script": "scripts/01_run.py",
                        "dependencies": [f"ingest_{slug}"],
                        "arguments": [
                            "--workspace",
                            "{workspace}",
                            "--step",
                            "convert",
                            "--region",
                            slug,
                            "--exchange-rates",
                            "{fixtures}/exchange_rates.json",
                        ],
                        "retries": 2,
                    }
                    for slug, _, _ in regions
                ],
                {
                    "intent_id": "aggregate_global_revenue",
                    "script": "scripts/01_run.py",
                    "dependencies": [f"convert_currency_{slug}" for slug, _, _ in regions],
                    "arguments": ["--workspace", "{workspace}", "--step", "aggregate"],
                    "retries": 2,
                },
            ],
            "scenarios": [{"name": "regional_revenue_run", "parameters": {}}],
        },
    )
    write_yaml(
        instance / "gold" / "assertions.yaml",
        {
            "assertions_version": "0.1.0",
            "pipeline_id": "multi_region_ecommerce_analytics",
            "scenarios": [
                {
                    "scenario": "regional_revenue_run",
                    "assertions": [
                        *[
                            {"assertion_id": f"{slug}_exported", "type": "json_path_equals", "path": f"artifacts/{slug}_ingest_status.json", "json_path": "rows_exported", "expected": 1}
                            for slug, _, _ in regions
                        ],
                        *[
                            {"assertion_id": f"{slug}_converted", "type": "json_path_equals", "path": f"artifacts/{slug}_convert_status.json", "json_path": "rows_converted", "expected": 1}
                            for slug, _, _ in regions
                        ],
                        {"assertion_id": "four_inputs_aggregated", "type": "json_path_equals", "path": "artifacts/aggregate_status.json", "json_path": "input_file_count", "expected": 4},
                        {"assertion_id": "global_revenue_total", "type": "json_path_equals", "path": "artifacts/aggregate_status.json", "json_path": "total_revenue_usd", "expected": 43230.0},
                        {"assertion_id": "global_report_has_four_regions", "type": "csv_row_count", "path": "artifacts/global_report.csv", "expected": 4},
                    ],
                }
            ],
        },
    )
    for slug, label, _ in regions:
        write_json(
            instance / "fixtures" / "inputs" / f"{slug}_database.json",
            {"driver": "filesystem-mock", "engine": "postgresql", "target": f"regional_sales_{slug}", "table": "sales", "region": label},
        )
    write_json(
        instance / "fixtures" / "inputs" / "exchange_rates.json",
        {
            "columns": ["currency", "rate_to_usd"],
            "rows": [
                {"currency": "USD", "rate_to_usd": 1.0},
                {"currency": "EUR", "rate_to_usd": 1.087},
                {"currency": "JPY", "rate_to_usd": 0.0067},
            ],
        },
    )
    write_json(instance / "contracts" / "artifacts" / "st.schema.json", status_schema())
    write_text(
        instance / "runtime" / "scripts" / "01_run.py",
        '''
        #!/usr/bin/env python3
        """Export, convert, and aggregate deterministic regional sales fixtures."""

        from __future__ import annotations

        import argparse
        import csv
        import json
        import shutil
        from decimal import Decimal, ROUND_HALF_UP
        from pathlib import Path


        REGIONS = ("us_east", "us_west", "eu", "apac")


        def read_rows(path: Path) -> list[dict[str, str]]:
            with path.open(encoding="utf-8", newline="") as handle:
                return list(csv.DictReader(handle))


        def main() -> None:
            parser = argparse.ArgumentParser()
            parser.add_argument("--workspace", type=Path, required=True)
            parser.add_argument("--step", choices=("export", "convert", "aggregate"), required=True)
            parser.add_argument("--region", choices=REGIONS)
            parser.add_argument("--database-resource", type=Path)
            parser.add_argument("--source-fixture", type=Path)
            parser.add_argument("--exchange-rates", type=Path)
            args = parser.parse_args()
            artifacts = args.workspace / "artifacts"
            artifacts.mkdir(parents=True, exist_ok=True)
            if args.step == "export":
                if not args.region or not args.database_resource or not args.source_fixture:
                    raise SystemExit("export requires region, database resource, and source fixture")
                resource = json.loads(args.database_resource.read_text(encoding="utf-8"))
                output = artifacts / f"{args.region}_sales.csv"
                shutil.copyfile(args.source_fixture, output)
                rows = read_rows(output)
                status = {"success": True, "region": resource["region"], "rows_exported": len(rows), "errors": []}
                (artifacts / f"{args.region}_ingest_status.json").write_text(json.dumps(status, indent=2) + "\\n", encoding="utf-8")
                return
            if args.step == "convert":
                if not args.region or not args.exchange_rates:
                    raise SystemExit("convert requires region and exchange rates")
                rate_document = json.loads(args.exchange_rates.read_text(encoding="utf-8"))
                rates = {row["currency"]: Decimal(str(row["rate_to_usd"])) for row in rate_document["rows"]}
                rows = read_rows(artifacts / f"{args.region}_sales.csv")
                output_rows = []
                for row in rows:
                    rate = rates[row["currency"]]
                    revenue = (Decimal(row["revenue"]) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    output_rows.append({"product_id": row["product_id"], "revenue_usd": f"{revenue:.2f}", "region": args.region})
                output = artifacts / f"{args.region}_usd.csv"
                with output.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=["product_id", "revenue_usd", "region"])
                    writer.writeheader()
                    writer.writerows(output_rows)
                status = {"success": True, "region": args.region, "rows_converted": len(output_rows), "errors": []}
                (artifacts / f"{args.region}_convert_status.json").write_text(json.dumps(status, indent=2) + "\\n", encoding="utf-8")
                return
            all_rows = []
            for region in REGIONS:
                all_rows.extend(read_rows(artifacts / f"{region}_usd.csv"))
            totals: dict[str, Decimal] = {}
            for row in all_rows:
                totals[row["region"]] = totals.get(row["region"], Decimal("0")) + Decimal(row["revenue_usd"])
            output = artifacts / "global_report.csv"
            with output.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["region", "total_revenue_usd"])
                writer.writeheader()
                for region in REGIONS:
                    writer.writerow({"region": region, "total_revenue_usd": f"{totals[region]:.2f}"})
            status = {
                "success": True,
                "input_file_count": len(REGIONS),
                "rows_aggregated": len(all_rows),
                "total_revenue_usd": float(sum(totals.values())),
                "errors": [],
            }
            (artifacts / "aggregate_status.json").write_text(json.dumps(status, indent=2) + "\\n", encoding="utf-8")


        if __name__ == "__main__":
            main()
        ''',
    )


def write_review_record() -> None:
    review_path = ROOT / "benchmark" / "reviews" / "main_batch_02" / "review_report.yaml"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_yaml(review_path) if review_path.is_file() else {}
    validation = existing.get(
        "validation",
        {
            "local_g0_g6": {"passed": 0, "failed": 0, "status": "pending"},
            "minikube_cluster_execution": "deferred",
        },
    )
    write_yaml(
        review_path,
        {
            "review_version": "0.1.0",
            "batch_id": "main_batch_02",
            "review_date": "2026-06-20",
            "status": "provisional",
            "review_method": "codex_assisted_structural_and_semantic_review",
            "independent_human_review": "pending",
            "pipelines": [
                {
                    "benchmark_id": "main:backup_strategy_selector",
                    "decisions": [
                        "Classified unknown start and completion markers as orchestration.",
                        "Represented the selected branch output as a conditional multi-producer backup artifact.",
                    ],
                    "outstanding_questions": [
                        "Confirm whether the original implementation has an incremental checkpoint input not described by the dataset."
                    ],
                },
                {
                    "benchmark_id": "main:fraud_detection_triage",
                    "decisions": ["Added explicit accounting for every source step without changing the reviewed branch bindings."],
                    "outstanding_questions": ["Confirm whether manual-review and payment-processing systems should become explicit external resources in a later catalogue release."],
                },
                {
                    "benchmark_id": "main:file_arrival_watcher",
                    "decisions": [
                        "Added an observed-missing-file scenario that gates validation and loading.",
                        "Bound the database loader to the original CSV after validation instead of an unproduced intermediate."
                    ],
                    "outstanding_questions": ["Confirm whether the missing-file state should be represented as a workflow failure rather than a completed timeout observation at cluster qualification."],
                },
                {
                    "benchmark_id": "main:database_replication_fanout",
                    "decisions": ["Restored explicit production, development, staging, and QA database resources and fixture-backed snapshot data."],
                    "outstanding_questions": ["Confirm source table, credential, and replace-vs-upsert semantics if original implementation evidence becomes available."],
                },
                {
                    "benchmark_id": "main:multi_region_ecommerce_analytics",
                    "decisions": [
                        "Classified unknown bookend markers as orchestration.",
                        "Corrected regional ingestion from a file loader to a database CSV exporter.",
                        "Bound all four converted CSVs to the aggregator cardinality-many input."
                    ],
                    "outstanding_questions": ["Confirm the intended EUR-to-USD rate convention and whether rates should vary by logical date."],
                },
            ],
            "validation": validation,
            "release_effect": {
                "annotation_status": "semantic_hardening_complete",
                "review_status": "independent_review_pending",
            },
        },
    )


def main() -> None:
    harden_backup_strategy()
    harden_fraud_triage()
    harden_file_arrival()
    harden_database_replication()
    harden_multi_region()
    update_manifest_statuses()
    write_review_record()
    print("semantic hardening batch 02 applied")


if __name__ == "__main__":
    main()
