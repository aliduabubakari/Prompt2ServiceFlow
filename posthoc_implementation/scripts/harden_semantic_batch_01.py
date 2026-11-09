#!/usr/bin/env python3
"""Apply reviewed semantic hardening to the first five complex Main-40 instances."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
INSTANCES = ROOT / "benchmark" / "instances" / "main"
HARDENED_BENCHMARK_IDS = {
    "main:airflow_db_cleanup",
    "main:global_dag",
    "main:pcd-etl",
    "main:etl_import_mondo",
    "main:WF_MAIN_DATASETS_LOAD_L2_TO_L2",
}


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_yaml(path: Path, document: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False, width=100), encoding="utf-8")


def write_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


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
        if benchmark_id not in HARDENED_BENCHMARK_IDS:
            continue
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


def artifact(
    artifact_id: str,
    name: str,
    data_type: str,
    *,
    producer: str | None,
    role: str = "intermediate",
    fixture_ref: str | None = None,
    schema_ref: str | None = None,
    sensitivity: str = "internal",
    persistence: str = "workflow",
    kind: str = "artifact",
    media_type: str = "application/json",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "artifact_id": artifact_id,
        "name": name,
        "kind": kind,
        "data_type": data_type,
        "media_type": media_type,
        "role": role,
        "producer": producer,
        "consumers": [],
        "sensitivity": sensitivity,
        "persistence": persistence,
    }
    if fixture_ref:
        result["fixture_ref"] = fixture_ref
    if schema_ref:
        result["schema_ref"] = schema_ref
    return result


def binding(
    intent_id: str,
    service_id: str,
    inputs: list[tuple[str, str]],
    outputs: list[tuple[str, str]],
    parameters: dict[str, Any],
    rationale: str,
    *,
    secrets: list[dict[str, str]] | None = None,
    confidence: str = "explicit",
) -> dict[str, Any]:
    return {
        "intent_id": intent_id,
        "service_id": service_id,
        "service_version": "1.0.0",
        "input_bindings": [
            {"port": port, "artifact_id": artifact_id} for port, artifact_id in inputs
        ],
        "output_bindings": [
            {"port": port, "artifact_id": artifact_id} for port, artifact_id in outputs
        ],
        "parameter_bindings": parameters,
        "secret_bindings": secrets or [],
        "rationale": rationale,
        "confidence": confidence,
    }


def configure_intent(
    serviceflow: dict[str, Any],
    intent_id: str,
    *,
    capability: str,
    inputs: list[str],
    outputs: list[str],
    external_system_refs: list[str],
    network_access: str,
    secret_access: str,
    rationale: str,
    category: str | None = None,
) -> None:
    intent = next(item for item in serviceflow["service_intents"] if item["intent_id"] == intent_id)
    intent["capability"] = capability
    intent["inputs"] = inputs
    intent["outputs"] = outputs
    intent["external_system_refs"] = external_system_refs
    intent["required_policy_properties"]["network_access"] = network_access
    intent["required_policy_properties"]["secret_access"] = secret_access
    intent["decomposition_rationale"] = rationale
    if category:
        intent["category"] = category


def remove_intents(serviceflow: dict[str, Any], intent_ids: set[str]) -> None:
    serviceflow["service_intents"] = [
        item for item in serviceflow["service_intents"] if item["intent_id"] not in intent_ids
    ]


def rebuild_consumers(serviceflow: dict[str, Any]) -> None:
    consumers: dict[str, list[str]] = {
        item["artifact_id"]: [] for item in serviceflow["artifacts"]
    }
    for intent in serviceflow["service_intents"]:
        for artifact_id in intent["inputs"]:
            consumers[artifact_id].append(intent["intent_id"])
    for item in serviceflow["artifacts"]:
        item["consumers"] = consumers[item["artifact_id"]]


def add_source_accounting(
    serviceflow: dict[str, Any],
    orchestration_refs: set[str] | None = None,
) -> None:
    orchestration_refs = orchestration_refs or set()
    spec_path = ROOT / "benchmark" / serviceflow["source"]["internal_spec_path"]
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    accounting = []
    for step in spec["steps"]:
        source_step_ref = step["step_id"]
        intent_ids = [
            intent["intent_id"]
            for intent in serviceflow["service_intents"]
            if source_step_ref in intent["source_step_refs"]
        ]
        if source_step_ref in orchestration_refs:
            disposition = "orchestration"
            intent_ids = []
            rationale = (
                "The source step controls workflow sequencing or failure handling and "
                "does not invoke a reusable catalogue service."
            )
        else:
            if not intent_ids:
                raise ValueError(
                    f"{serviceflow['composition_id']}: no service intent accounts for "
                    f"{source_step_ref}"
                )
            disposition = "service"
            rationale = "The source step invokes the reviewed service intent or intents listed."
        accounting.append(
            {
                "source_step_ref": source_step_ref,
                "disposition": disposition,
                "intent_ids": intent_ids,
                "rationale": rationale,
            }
        )
    serviceflow["source_step_accounting"] = accounting


def status_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": True,
        "required": ["success", "errors"],
        "properties": {
            "success": {"type": "boolean"},
            "errors": {"type": "array", "items": {"type": "string"}},
        },
    }


def harden_airflow_cleanup() -> None:
    instance = INSTANCES / "airflow_db_cleanup"
    path = instance / "gold" / "serviceflow.yaml"
    sf = load_yaml(path)
    cleanup_intents = [
        "cleanup_dag_run",
        "cleanup_task_instance",
        "cleanup_log",
        "cleanup_xcom",
        "cleanup_sla_miss",
        "cleanup_dag_model",
        "cleanup_task_reschedule",
        "cleanup_task_fail",
        "cleanup_rendered_task_instance_fields",
        "cleanup_import_error",
        "cleanup_base_job",
    ]
    table_names = {
        "cleanup_dag_run": ("DagRun", "dag_run", "execution_date"),
        "cleanup_task_instance": ("TaskInstance", "task_instance", "execution_date"),
        "cleanup_log": ("Log", "log", "dttm"),
        "cleanup_xcom": ("XCom", "xcom", "timestamp"),
        "cleanup_sla_miss": ("SlaMiss", "sla_miss", "execution_date"),
        "cleanup_dag_model": ("DagModel", "dag", "last_parsed_time"),
        "cleanup_task_reschedule": ("TaskReschedule", "task_reschedule", "reschedule_date"),
        "cleanup_task_fail": ("TaskFail", "task_fail", "end_date"),
        "cleanup_rendered_task_instance_fields": (
            "RenderedTaskInstanceFields",
            "rendered_task_instance_fields",
            "execution_date",
        ),
        "cleanup_import_error": ("ImportError", "import_error", "timestamp"),
        "cleanup_base_job": ("BaseJob", "job", "latest_heartbeat"),
    }

    sf["external_systems"] = [
        {
            "system_id": "airflow_metadata_database",
            "type": "database",
            "name": "Airflow metadata PostgreSQL database",
            "identifier": "airflow_metadata",
            "access_mode": "read_write",
            "authentication": "secret",
            "mock_strategy": "fixture",
        }
    ]
    configure_intent(
        sf,
        "print_configuration",
        capability="Resolve and validate the metadata-retention cutoff configuration.",
        inputs=["runtime_parameters"],
        outputs=["retention_config", "config_status"],
        external_system_refs=[],
        network_access="forbidden",
        secret_access="forbidden",
        rationale="The source step resolves the maximum metadata age and cleanup flags.",
        category="Transformer",
    )
    for intent_id in cleanup_intents:
        model_name, table_name, _ = table_names[intent_id]
        configure_intent(
            sf,
            intent_id,
            capability=f"Delete expired Airflow metadata rows from {model_name}.",
            inputs=["db_resource", "retention_config"],
            outputs=[
                intent_id.removeprefix("cleanup_") + "_status",
                intent_id.removeprefix("cleanup_") + "_result",
            ],
            external_system_refs=["airflow_metadata_database"],
            network_access="required",
            secret_access="required",
            rationale="This is an Airflow metadata retention operation, not session cleanup.",
            category="Maintenance",
        )
    configure_intent(
        sf,
        "cleanup_sessions",
        capability="Delete expired rows from the Airflow session table.",
        inputs=["db_resource"],
        outputs=["sessions_status", "sessions_result"],
        external_system_refs=["airflow_metadata_database"],
        network_access="required",
        secret_access="required",
        rationale="The session cleanup has a distinct expiration-table contract.",
    )
    configure_intent(
        sf,
        "analyze_query",
        capability="Refresh PostgreSQL optimizer statistics after all cleanup operations.",
        inputs=["db_resource"],
        outputs=["analyze_status"],
        external_system_refs=["airflow_metadata_database"],
        network_access="required",
        secret_access="required",
        rationale="The source explicitly runs database analysis after the cleanup fan-in.",
    )

    artifacts = [
        artifact(
            "runtime_parameters",
            "Cleanup runtime parameters",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/config.json",
            persistence="external",
            kind="external_resource",
        ),
        artifact(
            "retention_config",
            "Resolved retention configuration",
            "object",
            producer="print_configuration",
            schema_ref="contracts/artifacts/retention_config.schema.json",
        ),
        artifact(
            "config_status",
            "Configuration status",
            "status",
            producer="print_configuration",
            role="status",
            schema_ref="contracts/artifacts/st.schema.json",
        ),
        artifact(
            "db_resource",
            "Airflow metadata database",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/db.json",
            sensitivity="confidential",
            persistence="external",
            kind="external_resource",
        ),
    ]
    for intent_id in cleanup_intents:
        suffix = intent_id.removeprefix("cleanup_")
        artifacts.extend(
            [
                artifact(
                    f"{suffix}_status",
                    f"{suffix.replace('_', ' ').title()} cleanup status",
                    "status",
                    producer=intent_id,
                    role="status",
                    schema_ref="contracts/artifacts/st.schema.json",
                ),
                artifact(
                    f"{suffix}_result",
                    f"{suffix.replace('_', ' ').title()} affected table",
                    "table",
                    producer=intent_id,
                    schema_ref="contracts/artifacts/cleanup_result.schema.json",
                ),
            ]
        )
    artifacts.extend(
        [
            artifact(
                "sessions_status",
                "Session cleanup status",
                "status",
                producer="cleanup_sessions",
                role="status",
                schema_ref="contracts/artifacts/st.schema.json",
            ),
            artifact(
                "sessions_result",
                "Session cleanup affected table",
                "table",
                producer="cleanup_sessions",
                schema_ref="contracts/artifacts/cleanup_result.schema.json",
            ),
            artifact(
                "analyze_status",
                "Database analysis status",
                "status",
                producer="analyze_query",
                role="status",
                schema_ref="contracts/artifacts/st.schema.json",
            ),
        ]
    )
    sf["artifacts"] = artifacts

    bindings = [
        binding(
            "print_configuration",
            "retention_cutoff_config_resolver",
            [("runtime_parameters", "runtime_parameters")],
            [("retention_config", "retention_config"), ("config_status", "config_status")],
            {
                "max_age_parameter_name": "maxDBEntryAgeInDays",
                "max_age_variable_name": "airflow_db_cleanup__max_db_entry_age_in_days",
                "default_max_age_days": 30,
                "enable_delete": True,
                "print_deletes": False,
                "reference_time": "2026-01-31T00:00:00Z",
            },
            "Resolves the reviewed cutoff and deletion flags used by metadata cleanup tasks.",
        )
    ]
    for intent_id in cleanup_intents:
        model_name, table_name, age_column = table_names[intent_id]
        suffix = intent_id.removeprefix("cleanup_")
        parameters: dict[str, Any] = {
            "airflow_model_name": model_name,
            "table_name": table_name,
            "age_check_column": age_column,
            "keep_last": intent_id == "cleanup_dag_run",
        }
        if intent_id == "cleanup_import_error":
            parameters["do_not_delete_by_dag_id"] = True
        bindings.append(
            binding(
                intent_id,
                "airflow_metadata_retention_cleaner",
                [
                    ("airflow_metadata_database", "db_resource"),
                    ("retention_config", "retention_config"),
                ],
                [
                    ("cleanup_status", f"{suffix}_status"),
                    ("affected_table", f"{suffix}_result"),
                ],
                parameters,
                f"Applies Airflow-aware retention semantics to the {table_name} metadata table.",
            )
        )
    bindings.extend(
        [
            binding(
                "cleanup_sessions",
                "database_expired_session_cleanup",
                [("session_database", "db_resource")],
                [
                    ("session_cleanup_status", "sessions_status"),
                    ("affected_table", "sessions_result"),
                ],
                {
                    "session_table": "session",
                    "expiration_column": "expiry",
                    "delete_enabled": True,
                },
                "Uses the dedicated expired-session cleanup contract.",
            ),
            binding(
                "analyze_query",
                "database_statistics_analyzer",
                [("database", "db_resource")],
                [("analysis_status", "analyze_status")],
                {
                    "analysis_scope": "tables",
                    "table_names": [value[1] for value in table_names.values()] + ["session"],
                },
                "Refreshes optimizer statistics for every cleaned metadata table.",
            ),
        ]
    )
    sf["bindings"] = bindings
    add_source_accounting(sf)
    rebuild_consumers(sf)
    write_yaml(path, sf)

    tasks = []
    for intent in sf["service_intents"]:
        intent_id = intent["intent_id"]
        if intent_id == "print_configuration":
            step = "config"
            dependencies = []
        elif intent_id == "analyze_query":
            step = "analyze"
            dependencies = cleanup_intents + ["cleanup_sessions"]
        else:
            step = intent_id
            dependencies = [] if intent_id == "cleanup_sessions" else ["print_configuration"]
        task = {
            "intent_id": intent_id,
            "script": "scripts/01_run.py",
            "arguments": ["--workspace", "{workspace}", "--step", step],
            "retries": 1,
        }
        if dependencies:
            task["dependencies"] = dependencies
        tasks.append(task)
    write_yaml(
        instance / "runtime" / "manifest.yaml",
        {
            "runtime_manifest_version": "0.1.0",
            "pipeline_id": "airflow_db_cleanup",
            "image": "python:3.12-slim",
            "workflow_parameters": [],
            "tasks": tasks,
            "scenarios": [{"name": "run", "parameters": {}}],
            "cron": {"schedule": "0 0 * * *", "timezone": "UTC"},
        },
    )
    assertions = [
        {
            "assertion_id": "retention_cutoff_resolved",
            "type": "json_path_equals",
            "path": "artifacts/retention_config.json",
            "json_path": "max_age_days",
            "expected": 30,
        }
    ]
    for intent_id in cleanup_intents:
        suffix = intent_id.removeprefix("cleanup_")
        assertions.append(
            {
                "assertion_id": f"{suffix}_cleaned",
                "type": "json_path_equals",
                "path": f"artifacts/{suffix}_status.json",
                "json_path": "success",
                "expected": True,
            }
        )
    assertions.extend(
        [
            {
                "assertion_id": "sessions_cleaned",
                "type": "json_path_equals",
                "path": "artifacts/sessions_status.json",
                "json_path": "success",
                "expected": True,
            },
            {
                "assertion_id": "all_tables_analyzed",
                "type": "json_path_equals",
                "path": "artifacts/analyze_status.json",
                "json_path": "analyzed_table_count",
                "expected": 12,
            },
        ]
    )
    write_yaml(
        instance / "gold" / "assertions.yaml",
        {
            "assertions_version": "0.1.0",
            "pipeline_id": "airflow_db_cleanup",
            "scenarios": [{"scenario": "run", "assertions": assertions}],
        },
    )
    write_json(instance / "contracts" / "artifacts" / "st.schema.json", status_schema())
    write_json(
        instance / "contracts" / "artifacts" / "retention_config.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["max_age_days", "cutoff_date", "delete_enabled"],
            "properties": {
                "max_age_days": {"type": "integer", "minimum": 1},
                "cutoff_date": {"type": "string", "format": "date"},
                "delete_enabled": {"type": "boolean"},
            },
        },
    )
    write_json(
        instance / "contracts" / "artifacts" / "cleanup_result.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["table", "deleted_rows", "cutoff_date"],
            "properties": {
                "table": {"type": "string", "minLength": 1},
                "deleted_rows": {"type": "integer", "minimum": 0},
                "cutoff_date": {"type": "string", "format": "date"},
            },
        },
    )


def harden_global_dag() -> None:
    instance = INSTANCES / "global_dag"
    path = instance / "gold" / "serviceflow.yaml"
    sf = load_yaml(path)
    orchestration = {
        "start_global",
        "ingestion_pipeline.start",
        "ingestion_pipeline.end",
        "staging_pipeline.start",
        "staging_pipeline.staging_end",
        "end_global",
    }
    remove_intents(
        sf,
        {
            "start_global",
            "ingest_start",
            "ingest_end",
            "stage_begin",
            "stage_staging_end",
            "end_global",
            "stage_clean_tmp_death_redis",
        },
    )
    source_cleanup = next(
        item
        for item in sf["service_intents"]
        if item["intent_id"] == "stage_clean_tmp_death_files"
    )
    redis_cleanup = copy.deepcopy(source_cleanup)
    redis_cleanup["intent_id"] = "stage_clean_tmp_death_redis"
    redis_cleanup["name"] = "Clean temporary death Redis keys"
    redis_cleanup["capability"] = "Delete temporary Redis keys used for death-record staging."
    redis_cleanup["inputs"] = ["redis_resource"]
    redis_cleanup["outputs"] = ["stage_clean_tmp_death_redis_status"]
    redis_cleanup["external_system_refs"] = ["redis_database"]
    redis_cleanup["required_policy_properties"]["network_access"] = "required"
    redis_cleanup["required_policy_properties"]["secret_access"] = "optional"
    redis_cleanup["decomposition_rationale"] = (
        "The source cleanup step has independent filesystem and Redis cleanup effects."
    )
    sf["service_intents"].append(redis_cleanup)

    sf["external_systems"] = [
        {
            "system_id": "data_gouv_api",
            "type": "http_api",
            "name": "data.gouv.fr API",
            "identifier": "https://www.data.gouv.fr",
            "access_mode": "read",
            "authentication": "none",
            "mock_strategy": "fixture",
        },
        {
            "system_id": "postgres_database",
            "type": "database",
            "name": "PostgreSQL staging database",
            "identifier": "postgres_default",
            "access_mode": "read_write",
            "authentication": "secret",
            "mock_strategy": "fixture",
        },
        {
            "system_id": "redis_database",
            "type": "database",
            "name": "Redis staging database",
            "identifier": "redis:6379",
            "access_mode": "read_write",
            "authentication": "unknown",
            "mock_strategy": "fixture",
        },
        {
            "system_id": "workflow_filesystem",
            "type": "filesystem",
            "name": "Workflow filesystem",
            "identifier": "/workspace",
            "access_mode": "read_write",
            "authentication": "none",
            "mock_strategy": "fixture",
        },
    ]

    http_any = ["ingest_get_city_code_geo"]
    http_json = [
        "ingest_get_nuclear_json",
        "ingest_get_death_resource_list",
        "ingest_get_thermal_json",
    ]
    for intent_id in http_any:
        configure_intent(
            sf,
            intent_id,
            capability="Download the city-geography response artifact from data.gouv.fr.",
            inputs=["http_api_resource"],
            outputs=[f"{intent_id}_result", f"{intent_id}_status"],
            external_system_refs=["data_gouv_api"],
            network_access="required",
            secret_access="forbidden",
            rationale="The source response is CSV rather than a JSON-only API contract.",
            category="Extractor",
        )
    for intent_id in http_json:
        configure_intent(
            sf,
            intent_id,
            capability="Fetch and parse data.gouv.fr dataset metadata as JSON.",
            inputs=[],
            outputs=[f"{intent_id}_result", f"{intent_id}_status"],
            external_system_refs=["data_gouv_api"],
            network_access="required",
            secret_access="forbidden",
            rationale="These source endpoints return dataset metadata consumed by resource downloaders.",
            category="Extractor",
        )
    downloader_inputs = {
        "ingest_get_nuclear_data": "ingest_get_nuclear_json_result",
        "ingest_get_death_resources": "ingest_get_death_resource_list_result",
        "ingest_get_thermal_data": "ingest_get_thermal_json_result",
    }
    for intent_id, input_id in downloader_inputs.items():
        configure_intent(
            sf,
            intent_id,
            capability="Select and download data.gouv.fr dataset resources from metadata.",
            inputs=[input_id],
            outputs=[f"{intent_id}_result", f"{intent_id}_status"],
            external_system_refs=["data_gouv_api", "workflow_filesystem"],
            network_access="required",
            secret_access="forbidden",
            rationale="The source step resolves resource URLs from the preceding metadata artifact.",
            category="Extractor",
        )

    configure_intent(
        sf,
        "stage_import_nuclear_clean_data",
        capability="Normalize raw nuclear power-plant CSV into the staged canonical form.",
        inputs=["nuclear_raw_csv"],
        outputs=["nuclear_clean_csv", "stage_import_nuclear_clean_data_status"],
        external_system_refs=["workflow_filesystem"],
        network_access="forbidden",
        secret_access="forbidden",
        rationale="This source step is a CSV standardization operation.",
        category="Transformer",
    )
    configure_intent(
        sf,
        "stage_import_thermal_clean_data",
        capability="Normalize raw thermal power-plant CSV into the staged canonical form.",
        inputs=["thermal_raw_csv"],
        outputs=["thermal_clean_csv", "stage_import_thermal_clean_data_status"],
        external_system_refs=["workflow_filesystem"],
        network_access="forbidden",
        secret_access="forbidden",
        rationale="This source step is a CSV standardization operation.",
        category="Transformer",
    )
    for intent_id, sql_artifact, table_artifact in [
        (
            "stage_create_power_plants_table",
            "create_power_plants_sql",
            "power_plants_table",
        ),
        ("stage_create_death_table", "create_deaths_sql", "deaths_table"),
        ("stage_store_deaths_in_postgres", "death_insert_sql", "stored_deaths_table"),
        ("stage_store_plants_in_postgres", "plant_insert_sql", "stored_power_plants_table"),
    ]:
        configure_intent(
            sf,
            intent_id,
            capability="Execute the reviewed PostgreSQL SQL script for this staging step.",
            inputs=[sql_artifact, "postgres_database_resource"],
            outputs=[table_artifact, f"{intent_id}_status"],
            external_system_refs=["postgres_database"],
            network_access="required",
            secret_access="required",
            rationale="The source mechanism is explicit PostgreSQL SQL execution.",
            category="Loader",
        )
    configure_intent(
        sf,
        "stage_load_data_from_ingestion",
        capability="Load raw death-record files into Redis staging keys.",
        inputs=["death_source_files", "redis_resource"],
        outputs=["death_redis_keys", "stage_load_data_from_ingestion_status"],
        external_system_refs=["redis_database", "workflow_filesystem"],
        network_access="required",
        secret_access="optional",
        rationale="The source loads file batches into Redis and records imported files.",
        category="Loader",
    )
    configure_intent(
        sf,
        "stage_cleanse_death_data",
        capability="Generate PostgreSQL insert SQL from Redis death records and city geography.",
        inputs=["redis_resource", "city_geo_csv"],
        outputs=["death_insert_sql", "stage_cleanse_death_data_status"],
        external_system_refs=["redis_database", "workflow_filesystem"],
        network_access="required",
        secret_access="optional",
        rationale="The source cleans and enriches death records before rendering SQL.",
        category="Transformer",
    )
    configure_intent(
        sf,
        "stage_death_emptiness_check",
        capability="Check whether the generated death SQL artifact contains statements.",
        inputs=["death_sql_location"],
        outputs=[
            "stage_death_emptiness_check_decision",
            "stage_death_emptiness_check_status",
        ],
        external_system_refs=["workflow_filesystem"],
        network_access="optional",
        secret_access="optional",
        rationale="This is a file-availability and non-empty gate.",
        category="Sensor",
    )
    configure_intent(
        sf,
        "stage_clean_tmp_death_files",
        capability="Remove temporary death-record files and generated SQL.",
        inputs=[],
        outputs=["stage_clean_tmp_death_files_status"],
        external_system_refs=["workflow_filesystem"],
        network_access="forbidden",
        secret_access="forbidden",
        rationale="The filesystem cleanup effect is represented independently from Redis cleanup.",
        category="Maintenance",
    )
    configure_intent(
        sf,
        "stage_create_plant_persist_sql_query",
        capability="Render PostgreSQL insert SQL for cleaned power-plant CSV records.",
        inputs=["clean_power_plants_csv"],
        outputs=["plant_insert_sql", "stage_create_plant_persist_sql_query_status"],
        external_system_refs=["workflow_filesystem"],
        network_access="forbidden",
        secret_access="forbidden",
        rationale="The source step converts cleaned CSV records into PostgreSQL insert SQL.",
        category="Transformer",
    )

    st_schema = "contracts/artifacts/st.schema.json"
    artifacts = [
        artifact(
            "http_api_resource",
            "data.gouv API resource",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/http.json",
            persistence="external",
            kind="external_resource",
        ),
        artifact(
            "postgres_database_resource",
            "PostgreSQL database resource",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/db.json",
            persistence="external",
            sensitivity="confidential",
            kind="external_resource",
        ),
        artifact(
            "redis_resource",
            "Redis database resource",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/redis.json",
            persistence="external",
            kind="external_resource",
        ),
        artifact(
            "nuclear_raw_csv",
            "Raw nuclear plant CSV",
            "csv",
            producer=None,
            role="input",
            fixture_ref="fixtures/inputs/nuclear_raw.csv",
            persistence="external",
            media_type="text/csv",
        ),
        artifact(
            "thermal_raw_csv",
            "Raw thermal plant CSV",
            "csv",
            producer=None,
            role="input",
            fixture_ref="fixtures/inputs/thermal_raw.csv",
            persistence="external",
            media_type="text/csv",
        ),
        artifact(
            "city_geo_csv",
            "City geography CSV",
            "csv",
            producer=None,
            role="input",
            fixture_ref="fixtures/inputs/city_geo.csv",
            persistence="external",
            media_type="text/csv",
        ),
        artifact(
            "death_source_files",
            "Raw death-record file batch",
            "text",
            producer=None,
            role="input",
            fixture_ref="fixtures/inputs/death_records.txt",
            persistence="external",
            media_type="text/plain",
        ),
        artifact(
            "create_power_plants_sql",
            "Create power plants SQL",
            "text",
            producer=None,
            role="input",
            fixture_ref="fixtures/inputs/create_power_plants.sql",
            persistence="external",
            media_type="text/plain",
        ),
        artifact(
            "create_deaths_sql",
            "Create deaths SQL",
            "text",
            producer=None,
            role="input",
            fixture_ref="fixtures/inputs/create_deaths.sql",
            persistence="external",
            media_type="text/plain",
        ),
        artifact(
            "death_sql_location",
            "Generated death SQL location",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/death_sql_location.json",
            persistence="external",
            kind="external_resource",
        ),
        artifact(
            "clean_power_plants_csv",
            "Combined cleaned power-plant CSV",
            "csv",
            producer=None,
            role="input",
            fixture_ref="fixtures/inputs/clean_power_plants.csv",
            persistence="external",
            media_type="text/csv",
        ),
    ]
    for intent_id in http_any:
        artifacts.extend(
            [
                artifact(
                    f"{intent_id}_result",
                    "City geography response artifact",
                    "any",
                    producer=intent_id,
                ),
                artifact(
                    f"{intent_id}_status",
                    "City geography extraction status",
                    "status",
                    producer=intent_id,
                    role="status",
                    schema_ref=st_schema,
                ),
            ]
        )
    for intent_id in http_json:
        artifacts.extend(
            [
                artifact(
                    f"{intent_id}_result",
                    f"{intent_id} metadata JSON",
                    "json",
                    producer=intent_id,
                    schema_ref="contracts/artifacts/api_metadata.schema.json",
                ),
                artifact(
                    f"{intent_id}_status",
                    f"{intent_id} extraction status",
                    "status",
                    producer=intent_id,
                    role="status",
                    schema_ref=st_schema,
                ),
            ]
        )
    for intent_id in downloader_inputs:
        artifacts.extend(
            [
                artifact(
                    f"{intent_id}_result",
                    f"{intent_id} downloaded files",
                    "array",
                    producer=intent_id,
                    schema_ref="contracts/artifacts/downloaded_files.schema.json",
                ),
                artifact(
                    f"{intent_id}_status",
                    f"{intent_id} download status",
                    "status",
                    producer=intent_id,
                    role="status",
                    schema_ref=st_schema,
                ),
            ]
        )
    artifacts.extend(
        [
            artifact(
                "nuclear_clean_csv",
                "Clean nuclear plant CSV",
                "csv",
                producer="stage_import_nuclear_clean_data",
                media_type="text/csv",
            ),
            artifact(
                "stage_import_nuclear_clean_data_status",
                "Nuclear CSV transform status",
                "status",
                producer="stage_import_nuclear_clean_data",
                role="status",
                schema_ref=st_schema,
            ),
            artifact(
                "thermal_clean_csv",
                "Clean thermal plant CSV",
                "csv",
                producer="stage_import_thermal_clean_data",
                media_type="text/csv",
            ),
            artifact(
                "stage_import_thermal_clean_data_status",
                "Thermal CSV transform status",
                "status",
                producer="stage_import_thermal_clean_data",
                role="status",
                schema_ref=st_schema,
            ),
            artifact(
                "power_plants_table",
                "Created power plants table",
                "table",
                producer="stage_create_power_plants_table",
                schema_ref="contracts/artifacts/table_result.schema.json",
            ),
            artifact(
                "stage_create_power_plants_table_status",
                "Create power plants table status",
                "status",
                producer="stage_create_power_plants_table",
                role="status",
                schema_ref=st_schema,
            ),
            artifact(
                "deaths_table",
                "Created deaths table",
                "table",
                producer="stage_create_death_table",
                schema_ref="contracts/artifacts/table_result.schema.json",
            ),
            artifact(
                "stage_create_death_table_status",
                "Create deaths table status",
                "status",
                producer="stage_create_death_table",
                role="status",
                schema_ref=st_schema,
            ),
            artifact(
                "death_redis_keys",
                "Death-record Redis key references",
                "object",
                producer="stage_load_data_from_ingestion",
                schema_ref="contracts/artifacts/redis_keys.schema.json",
            ),
            artifact(
                "stage_load_data_from_ingestion_status",
                "Redis load status",
                "status",
                producer="stage_load_data_from_ingestion",
                role="status",
                schema_ref=st_schema,
            ),
            artifact(
                "death_insert_sql",
                "Generated death insert SQL",
                "text",
                producer="stage_cleanse_death_data",
                media_type="text/plain",
            ),
            artifact(
                "stage_cleanse_death_data_status",
                "Death SQL generation status",
                "status",
                producer="stage_cleanse_death_data",
                role="status",
                schema_ref=st_schema,
            ),
            artifact(
                "stage_death_emptiness_check_decision",
                "Death SQL content decision",
                "decision",
                producer="stage_death_emptiness_check",
                role="decision",
                schema_ref="contracts/artifacts/death_decision.schema.json",
            ),
            artifact(
                "stage_death_emptiness_check_status",
                "Death SQL check status",
                "status",
                producer="stage_death_emptiness_check",
                role="status",
                schema_ref=st_schema,
            ),
            artifact(
                "stored_deaths_table",
                "Stored deaths table",
                "table",
                producer="stage_store_deaths_in_postgres",
                schema_ref="contracts/artifacts/table_result.schema.json",
            ),
            artifact(
                "stage_store_deaths_in_postgres_status",
                "Store deaths status",
                "status",
                producer="stage_store_deaths_in_postgres",
                role="status",
                schema_ref=st_schema,
            ),
            artifact(
                "stage_clean_tmp_death_files_status",
                "Temporary death file cleanup status",
                "status",
                producer="stage_clean_tmp_death_files",
                role="status",
                schema_ref=st_schema,
            ),
            artifact(
                "stage_clean_tmp_death_redis_status",
                "Temporary death Redis cleanup status",
                "status",
                producer="stage_clean_tmp_death_redis",
                role="status",
                schema_ref=st_schema,
            ),
            artifact(
                "plant_insert_sql",
                "Generated plant insert SQL",
                "text",
                producer="stage_create_plant_persist_sql_query",
                media_type="text/plain",
            ),
            artifact(
                "stage_create_plant_persist_sql_query_status",
                "Plant SQL generation status",
                "status",
                producer="stage_create_plant_persist_sql_query",
                role="status",
                schema_ref=st_schema,
            ),
            artifact(
                "stored_power_plants_table",
                "Stored power plants table",
                "table",
                producer="stage_store_plants_in_postgres",
                schema_ref="contracts/artifacts/table_result.schema.json",
            ),
            artifact(
                "stage_store_plants_in_postgres_status",
                "Store power plants status",
                "status",
                producer="stage_store_plants_in_postgres",
                role="status",
                schema_ref=st_schema,
            ),
        ]
    )
    sf["artifacts"] = artifacts

    bindings = []
    bindings.append(
        binding(
            "ingest_get_city_code_geo",
            "http_api_request_artifact_extractor",
            [("http_api_resource", "http_api_resource")],
            [
                ("response_artifact", "ingest_get_city_code_geo_result"),
                ("extraction_status", "ingest_get_city_code_geo_status"),
            ],
            {
                "endpoint": "/resources/communes-de-france.csv",
                "method": "GET",
                "expected_content_types": ["text/csv"],
                "output_name": "city_geo_loc.csv",
            },
            "The city-geography endpoint returns a CSV artifact rather than JSON.",
        )
    )
    for intent_id, endpoint in [
        ("ingest_get_nuclear_json", "/api/1/datasets/nuclear"),
        ("ingest_get_death_resource_list", "/api/1/datasets/deaths"),
        ("ingest_get_thermal_json", "/api/1/datasets/thermal"),
    ]:
        bindings.append(
            binding(
                intent_id,
                "http_json_request_extractor",
                [],
                [
                    ("response_json", f"{intent_id}_result"),
                    ("extraction_status", f"{intent_id}_status"),
                ],
                {"base_url": "https://www.data.gouv.fr", "endpoint": endpoint, "method": "GET"},
                "The endpoint returns JSON dataset metadata used by the next downloader.",
            )
        )
    for intent_id, input_id, selector, output_name in [
        (
            "ingest_get_nuclear_data",
            "ingest_get_nuclear_json_result",
            {"format": "csv", "name_contains": "nuclear"},
            "nuclear-{resource_name}",
        ),
        (
            "ingest_get_death_resources",
            "ingest_get_death_resource_list_result",
            {"format": "txt"},
            "death-{index}.txt",
        ),
        (
            "ingest_get_thermal_data",
            "ingest_get_thermal_json_result",
            {"format": "csv", "name_contains": "thermal"},
            "thermal-{resource_name}",
        ),
    ]:
        bindings.append(
            binding(
                intent_id,
                "data_gouv_dataset_resource_downloader",
                [("dataset_metadata_json", input_id)],
                [
                    ("downloaded_files", f"{intent_id}_result"),
                    ("download_status", f"{intent_id}_status"),
                ],
                {
                    "resource_selector": selector,
                    "max_resources": 5 if intent_id == "ingest_get_death_resources" else 1,
                    "output_name_template": output_name,
                },
                "Selects and downloads the resources described by the preceding metadata.",
            )
        )
    for intent_id, input_id, output_id, plant_type in [
        (
            "stage_import_nuclear_clean_data",
            "nuclear_raw_csv",
            "nuclear_clean_csv",
            "nuclear",
        ),
        (
            "stage_import_thermal_clean_data",
            "thermal_raw_csv",
            "thermal_clean_csv",
            "thermal",
        ),
    ]:
        bindings.append(
            binding(
                intent_id,
                "power_plant_csv_standardizer",
                [("raw_power_plant_csv", input_id)],
                [
                    ("clean_power_plant_csv", output_id),
                    ("transform_status", f"{intent_id}_status"),
                ],
                {
                    "plant_type": plant_type,
                    "column_mapping": {
                        "name": "plant_name",
                        "capacity": "capacity_mw",
                    },
                    "output_path": f"/workspace/artifacts/{output_id}.csv",
                },
                f"Applies the reviewed canonical mapping for {plant_type} plant CSV data.",
            )
        )
    for intent_id, sql_id, table_id, target in [
        (
            "stage_create_power_plants_table",
            "create_power_plants_sql",
            "power_plants_table",
            ["power_plants"],
        ),
        ("stage_create_death_table", "create_deaths_sql", "deaths_table", ["deaths"]),
        (
            "stage_store_deaths_in_postgres",
            "death_insert_sql",
            "stored_deaths_table",
            ["deaths"],
        ),
        (
            "stage_store_plants_in_postgres",
            "plant_insert_sql",
            "stored_power_plants_table",
            ["power_plants"],
        ),
    ]:
        bindings.append(
            binding(
                intent_id,
                "postgres_sql_file_executor",
                [
                    ("sql_script_file", sql_id),
                    ("postgres_database", "postgres_database_resource"),
                ],
                [
                    ("affected_tables", table_id),
                    ("execution_status", f"{intent_id}_status"),
                ],
                {
                    "target_tables": target,
                    "transaction_mode": "single_transaction",
                    "statement_type": "DDL" if "create_" in intent_id else "DML",
                },
                "Executes the reviewed SQL artifact against PostgreSQL.",
            )
        )
    bindings.extend(
        [
            binding(
                "stage_load_data_from_ingestion",
                "redis_file_batch_loader",
                [
                    ("source_files", "death_source_files"),
                    ("redis_resource", "redis_resource"),
                ],
                [
                    ("redis_key_references", "death_redis_keys"),
                    ("load_status", "stage_load_data_from_ingestion_status"),
                ],
                {
                    "raw_records_key": "death_raw",
                    "imported_files_key": "imported_death_files",
                    "write_mode": "replace",
                },
                "Loads death-record file batches into the two source Redis keys.",
            ),
            binding(
                "stage_cleanse_death_data",
                "french_death_records_sql_script_generator",
                [
                    ("redis_resource", "redis_resource"),
                    ("city_geo_csv", "city_geo_csv"),
                ],
                [
                    ("death_insert_sql_file", "death_insert_sql"),
                    ("generation_status", "stage_cleanse_death_data_status"),
                ],
                {
                    "raw_records_key": "death_raw",
                    "target_table": "deaths",
                    "output_path": "/workspace/artifacts/death_insert_sql.sql",
                },
                "Cleans French death records and renders the PostgreSQL insert script.",
            ),
            binding(
                "stage_death_emptiness_check",
                "file_location_availability_sensor",
                [("file_location_resource", "death_sql_location")],
                [
                    ("availability_decision", "stage_death_emptiness_check_decision"),
                    ("check_status", "stage_death_emptiness_check_status"),
                ],
                {
                    "location_type": "filesystem",
                    "path": "/workspace/artifacts/death_insert_sql.sql",
                    "availability_condition": "non_empty",
                },
                "Checks the generated SQL file before the conditional PostgreSQL load.",
            ),
            binding(
                "stage_clean_tmp_death_files",
                "temporary_resource_cleanup",
                [],
                [("cleanup_status", "stage_clean_tmp_death_files_status")],
                {
                    "targets": [
                        "/workspace/artifacts/death_insert_sql.sql",
                        "/workspace/raw/death",
                    ],
                    "ignore_missing": True,
                },
                "Removes temporary death-record files after a successful store.",
            ),
            binding(
                "stage_clean_tmp_death_redis",
                "redis_key_cleanup",
                [("redis_resource", "redis_resource")],
                [("redis_cleanup_status", "stage_clean_tmp_death_redis_status")],
                {
                    "keys": ["death_raw", "imported_death_files"],
                    "action": "delete",
                    "ignore_missing": True,
                },
                "Removes temporary Redis keys independently from filesystem cleanup.",
            ),
            binding(
                "stage_create_plant_persist_sql_query",
                "tabular_csv_postgres_insert_sql_generator",
                [("source_csv_files", "clean_power_plants_csv")],
                [
                    ("insert_sql_file", "plant_insert_sql"),
                    ("generation_status", "stage_create_plant_persist_sql_query_status"),
                ],
                {
                    "target_table": "power_plants",
                    "insert_mode": "insert",
                    "output_path": "/workspace/artifacts/plant_insert_sql.sql",
                },
                "Renders PostgreSQL inserts for the cleaned power-plant records.",
            ),
        ]
    )
    sf["bindings"] = bindings

    ingestion_roots = [
        "ingest_get_city_code_geo",
        "ingest_get_nuclear_json",
        "ingest_get_death_resource_list",
        "ingest_get_thermal_json",
    ]
    ingestion_terminals = [
        "ingest_get_city_code_geo",
        "ingest_get_nuclear_data",
        "ingest_get_death_resources",
        "ingest_get_thermal_data",
    ]
    staging_roots = [
        "stage_import_nuclear_clean_data",
        "stage_import_thermal_clean_data",
        "stage_create_power_plants_table",
        "stage_create_death_table",
    ]
    edges = [
        {"from": "ingest_get_nuclear_json", "to": "ingest_get_nuclear_data"},
        {
            "from": "ingest_get_death_resource_list",
            "to": "ingest_get_death_resources",
        },
        {"from": "ingest_get_thermal_json", "to": "ingest_get_thermal_data"},
    ]
    edges.extend(
        {"from": source, "to": target}
        for source in ingestion_terminals
        for target in staging_roots
    )
    edges.extend(
        [
            {
                "from": "stage_import_nuclear_clean_data",
                "to": "stage_import_thermal_clean_data",
            },
            {
                "from": "stage_import_thermal_clean_data",
                "to": "stage_create_power_plants_table",
            },
            {
                "from": "stage_create_power_plants_table",
                "to": "stage_create_plant_persist_sql_query",
            },
            {
                "from": "stage_create_plant_persist_sql_query",
                "to": "stage_store_plants_in_postgres",
            },
            {
                "from": "stage_create_death_table",
                "to": "stage_load_data_from_ingestion",
            },
            {
                "from": "stage_load_data_from_ingestion",
                "to": "stage_cleanse_death_data",
            },
            {
                "from": "stage_cleanse_death_data",
                "to": "stage_death_emptiness_check",
            },
            {
                "from": "stage_death_emptiness_check",
                "to": "stage_store_deaths_in_postgres",
                "condition": "has_content == true",
            },
            {
                "from": "stage_store_deaths_in_postgres",
                "to": "stage_clean_tmp_death_files",
            },
            {
                "from": "stage_store_deaths_in_postgres",
                "to": "stage_clean_tmp_death_redis",
            },
        ]
    )
    sf["control_flow"] = {
        "edges": edges,
        "parallel_groups": [
            {"group_id": "ingestion_parallel", "intent_ids": ingestion_roots},
            {
                "group_id": "death_cleanup_parallel",
                "intent_ids": [
                    "stage_clean_tmp_death_files",
                    "stage_clean_tmp_death_redis",
                ],
            },
        ],
        "branches": [],
        "gates": [
            {
                "gate_id": "death_sql_non_empty",
                "sensor_intent": "stage_death_emptiness_check",
                "condition": "has_content == true",
                "gated_intents": [
                    "stage_store_deaths_in_postgres",
                    "stage_clean_tmp_death_files",
                    "stage_clean_tmp_death_redis",
                ],
            }
        ],
    }
    add_source_accounting(sf, orchestration)
    rebuild_consumers(sf)
    write_yaml(path, sf)

    tasks = []
    task_dependencies: dict[str, list[str]] = {
        "ingest_get_nuclear_data": ["ingest_get_nuclear_json"],
        "ingest_get_death_resources": ["ingest_get_death_resource_list"],
        "ingest_get_thermal_data": ["ingest_get_thermal_json"],
        "stage_import_nuclear_clean_data": ingestion_terminals,
        "stage_import_thermal_clean_data": [
            *ingestion_terminals,
            "stage_import_nuclear_clean_data",
        ],
        "stage_create_power_plants_table": [
            *ingestion_terminals,
            "stage_import_thermal_clean_data",
        ],
        "stage_create_death_table": ingestion_terminals,
        "stage_load_data_from_ingestion": ["stage_create_death_table"],
        "stage_cleanse_death_data": ["stage_load_data_from_ingestion"],
        "stage_death_emptiness_check": ["stage_cleanse_death_data"],
        "stage_store_deaths_in_postgres": ["stage_death_emptiness_check"],
        "stage_clean_tmp_death_files": ["stage_store_deaths_in_postgres"],
        "stage_clean_tmp_death_redis": ["stage_store_deaths_in_postgres"],
        "stage_create_plant_persist_sql_query": ["stage_create_power_plants_table"],
        "stage_store_plants_in_postgres": ["stage_create_plant_persist_sql_query"],
    }
    for intent in sf["service_intents"]:
        intent_id = intent["intent_id"]
        task: dict[str, Any] = {
            "intent_id": intent_id,
            "script": "scripts/01_run.py",
            "arguments": ["--workspace", "{workspace}", "--step", intent_id],
        }
        if intent_id in task_dependencies:
            task["dependencies"] = task_dependencies[intent_id]
        if intent_id == "stage_death_emptiness_check":
            task["arguments"].extend(
                ["--death-records-available", "{death_records_available}"]
            )
            task["output_parameters"] = [
                {
                    "name": "has-content",
                    "path": "/workspace/artifacts/death_sql_has_content.txt",
                }
            ]
        if intent_id in {
            "stage_store_deaths_in_postgres",
            "stage_clean_tmp_death_files",
            "stage_clean_tmp_death_redis",
        }:
            task["when"] = (
                "{{tasks.stage_death_emptiness_check.outputs.parameters.has-content}} == true"
            )
            task["local_condition"] = {
                "path": "artifacts/stage_death_emptiness_check_decision.json",
                "json_path": "has_content",
                "equals": True,
            }
        tasks.append(task)
    write_yaml(
        instance / "runtime" / "manifest.yaml",
        {
            "runtime_manifest_version": "0.1.0",
            "pipeline_id": "global_dag",
            "image": "python:3.12-slim",
            "workflow_parameters": [
                {"name": "death-records-available", "default": True}
            ],
            "tasks": tasks,
            "scenarios": [
                {"name": "death_records_present", "parameters": {"death_records_available": True}},
                {"name": "death_records_empty", "parameters": {"death_records_available": False}},
            ],
        },
    )
    write_yaml(
        instance / "gold" / "assertions.yaml",
        {
            "assertions_version": "0.1.0",
            "pipeline_id": "global_dag",
            "scenarios": [
                {
                    "scenario": "death_records_present",
                    "assertions": [
                        {
                            "assertion_id": "metadata_downloaded",
                            "type": "json_path_equals",
                            "path": "artifacts/ingest_get_nuclear_json_status.json",
                            "json_path": "success",
                            "expected": True,
                        },
                        {
                            "assertion_id": "death_resources_selected",
                            "type": "json_array_length",
                            "path": "artifacts/ingest_get_death_resources_result.json",
                            "json_path": "files",
                            "expected": 2,
                        },
                        {
                            "assertion_id": "death_sql_has_content",
                            "type": "json_path_equals",
                            "path": "artifacts/stage_death_emptiness_check_decision.json",
                            "json_path": "has_content",
                            "expected": True,
                        },
                        {
                            "assertion_id": "deaths_stored",
                            "type": "json_path_equals",
                            "path": "artifacts/stage_store_deaths_in_postgres_status.json",
                            "json_path": "success",
                            "expected": True,
                        },
                        {
                            "assertion_id": "redis_cleaned",
                            "type": "json_path_equals",
                            "path": "artifacts/stage_clean_tmp_death_redis_status.json",
                            "json_path": "success",
                            "expected": True,
                        },
                        {
                            "assertion_id": "plants_stored",
                            "type": "json_path_equals",
                            "path": "artifacts/stage_store_plants_in_postgres_status.json",
                            "json_path": "success",
                            "expected": True,
                        },
                    ],
                },
                {
                    "scenario": "death_records_empty",
                    "assertions": [
                        {
                            "assertion_id": "death_sql_empty",
                            "type": "json_path_equals",
                            "path": "artifacts/stage_death_emptiness_check_decision.json",
                            "json_path": "has_content",
                            "expected": False,
                        },
                        {
                            "assertion_id": "death_store_skipped",
                            "type": "file_absent",
                            "path": "artifacts/stage_store_deaths_in_postgres_status.json",
                        },
                        {
                            "assertion_id": "death_cleanup_skipped",
                            "type": "file_absent",
                            "path": "artifacts/stage_clean_tmp_death_files_status.json",
                        },
                        {
                            "assertion_id": "plant_branch_completed",
                            "type": "json_path_equals",
                            "path": "artifacts/stage_store_plants_in_postgres_status.json",
                            "json_path": "success",
                            "expected": True,
                        },
                    ],
                },
            ],
        },
    )
    contracts = instance / "contracts" / "artifacts"
    write_json(contracts / "st.schema.json", status_schema())
    write_json(
        contracts / "api_metadata.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["dataset_id", "resources"],
            "properties": {
                "dataset_id": {"type": "string"},
                "resources": {"type": "array"},
            },
        },
    )
    write_json(
        contracts / "downloaded_files.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["files"],
            "properties": {
                "files": {"type": "array", "items": {"type": "string"}},
            },
        },
    )
    write_json(
        contracts / "death_decision.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["has_content", "success"],
            "properties": {
                "has_content": {"type": "boolean"},
                "success": {"const": True},
            },
        },
    )
    write_json(
        contracts / "table_result.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["tables", "row_count"],
            "properties": {
                "tables": {"type": "array", "items": {"type": "string"}},
                "row_count": {"type": "integer", "minimum": 0},
            },
        },
    )
    write_json(
        contracts / "redis_keys.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["keys"],
            "properties": {"keys": {"type": "array", "items": {"type": "string"}}},
        },
    )


def harden_pcd_etl() -> None:
    instance = INSTANCES / "pcd_etl"
    path = instance / "gold" / "serviceflow.yaml"
    sf = load_yaml(path)
    remove_intents(sf, {"start_pcd_extract_1", "start_pcd_extract_2"})
    first_phase = [
        "status_tracker",
        "financial_expense",
        "upcc_financial_reporting",
        "chc_financial_reporting",
        "pcn_financial_reporting",
        "nppcc_financial_reporting",
        "fiscal_year_reporting_dates",
        "upcc_primary_care_patient_services",
        "chc_primary_care_patient_services",
        "practitioner_role_mapping",
    ]
    second_phase = [
        "provincial_risk_tracking",
        "decision_log",
        "ha_hierarchy",
        "hr_records",
        "uppc_budget",
        "chc_budget",
        "pcn_budget",
        "nppcc_budget",
    ]
    api_intents = first_phase + second_phase
    sf["external_systems"] = [
        {
            "system_id": "pcd_sftp",
            "type": "sftp",
            "name": "PCD SFTP drop zone",
            "identifier": "/data/pcd",
            "access_mode": "read",
            "authentication": "secret",
            "mock_strategy": "fixture",
        },
        {
            "system_id": "pcd_shared_folder",
            "type": "filesystem",
            "name": "PCD shared folder",
            "identifier": "/data/pcd",
            "access_mode": "read",
            "authentication": "none",
            "mock_strategy": "fixture",
        },
        {
            "system_id": "pcd_api",
            "type": "http_api",
            "name": "PCD API",
            "identifier": "https://pcd.example.test",
            "access_mode": "read",
            "authentication": "secret",
            "mock_strategy": "fixture",
        },
        {
            "system_id": "kubernetes_cluster",
            "type": "cloud_service",
            "name": "PCD Kubernetes cluster",
            "identifier": "pcd-jobs",
            "access_mode": "invoke",
            "authentication": "secret",
            "mock_strategy": "fixture",
        },
        {
            "system_id": "email_service",
            "type": "email",
            "name": "PCD notification service",
            "identifier": "pcd-email",
            "access_mode": "invoke",
            "authentication": "unknown",
            "mock_strategy": "fixture",
        },
    ]
    configure_intent(
        sf,
        "check_pcd_sftp_folder",
        capability="Check whether the PCD SFTP location contains an available input batch.",
        inputs=["pcd_sftp_resource"],
        outputs=["check_pcd_sftp_folder_decision", "check_pcd_sftp_folder_status"],
        external_system_refs=["pcd_sftp"],
        network_access="optional",
        secret_access="optional",
        rationale="The source Kubernetes check is represented as the reusable location sensor effect.",
        category="Sensor",
    )
    configure_intent(
        sf,
        "check_pcd_shared_folder",
        capability="Check whether the PCD shared folder contains an available input batch.",
        inputs=["pcd_shared_folder_resource"],
        outputs=["check_pcd_shared_folder_decision", "check_pcd_shared_folder_status"],
        external_system_refs=["pcd_shared_folder"],
        network_access="optional",
        secret_access="optional",
        rationale="The source Kubernetes check is represented as the reusable location sensor effect.",
        category="Sensor",
    )
    for intent_id in api_intents:
        configure_intent(
            sf,
            intent_id,
            capability=f"Extract the {intent_id.replace('_', ' ')} dataset from the PCD API.",
            inputs=["pcd_api_resource"],
            outputs=[f"{intent_id}_result", f"{intent_id}_status"],
            external_system_refs=["pcd_api"],
            network_access="required",
            secret_access="optional",
            rationale="The source mechanism is an HTTP request and returns an API response artifact.",
            category="Extractor",
        )
    configure_intent(
        sf,
        "pcd_file_upload",
        capability="Submit and wait for the configured PCD file-processing Kubernetes Job.",
        inputs=["kubernetes_cluster_resource", "pcd_job_template"],
        outputs=["pcd_file_upload_result", "pcd_file_upload_status"],
        external_system_refs=["kubernetes_cluster"],
        network_access="required",
        secret_access="required",
        rationale="The source explicitly invokes a caller-supplied Kubernetes Job template.",
        category="ExternalWorkflowAdapter",
    )
    configure_intent(
        sf,
        "etl_notification",
        capability="Send the PCD ETL completion notification.",
        inputs=["email_resource"],
        outputs=["etl_notification_status"],
        external_system_refs=["email_service"],
        network_access="required",
        secret_access="optional",
        rationale="The final source step is an email notification.",
        category="Notifier",
    )

    st_schema = "contracts/artifacts/st.schema.json"
    artifacts = [
        artifact(
            "pcd_sftp_resource",
            "PCD SFTP resource",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/sftp.json",
            persistence="external",
            kind="external_resource",
        ),
        artifact(
            "pcd_shared_folder_resource",
            "PCD shared-folder resource",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/shared_folder.json",
            persistence="external",
            kind="external_resource",
        ),
        artifact(
            "pcd_api_resource",
            "PCD API resource",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/api.json",
            persistence="external",
            sensitivity="confidential",
            kind="external_resource",
        ),
        artifact(
            "kubernetes_cluster_resource",
            "Kubernetes cluster resource",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/kubernetes.json",
            persistence="external",
            sensitivity="confidential",
            kind="external_resource",
        ),
        artifact(
            "pcd_job_template",
            "PCD Kubernetes Job template",
            "text",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/pcd_job.yaml",
            persistence="external",
            media_type="application/yaml",
        ),
        artifact(
            "email_resource",
            "Email service resource",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/email.json",
            persistence="external",
            kind="external_resource",
        ),
    ]
    for intent_id in ["check_pcd_sftp_folder", "check_pcd_shared_folder"]:
        artifacts.extend(
            [
                artifact(
                    f"{intent_id}_decision",
                    f"{intent_id} availability decision",
                    "decision",
                    producer=intent_id,
                    role="decision",
                    schema_ref="contracts/artifacts/availability.schema.json",
                ),
                artifact(
                    f"{intent_id}_status",
                    f"{intent_id} check status",
                    "status",
                    producer=intent_id,
                    role="status",
                    schema_ref=st_schema,
                ),
            ]
        )
    for intent_id in api_intents:
        artifacts.extend(
            [
                artifact(
                    f"{intent_id}_result",
                    f"{intent_id} API result",
                    "any",
                    producer=intent_id,
                    schema_ref="contracts/artifacts/api_result.schema.json",
                ),
                artifact(
                    f"{intent_id}_status",
                    f"{intent_id} extraction status",
                    "status",
                    producer=intent_id,
                    role="status",
                    schema_ref=st_schema,
                ),
            ]
        )
    artifacts.extend(
        [
            artifact(
                "pcd_file_upload_result",
                "PCD Kubernetes Job reference",
                "object",
                producer="pcd_file_upload",
                schema_ref="contracts/artifacts/job_reference.schema.json",
            ),
            artifact(
                "pcd_file_upload_status",
                "PCD Kubernetes Job status",
                "status",
                producer="pcd_file_upload",
                role="status",
                schema_ref=st_schema,
            ),
            artifact(
                "etl_notification_status",
                "PCD ETL notification status",
                "notification",
                producer="etl_notification",
                role="status",
                schema_ref="contracts/artifacts/notification.schema.json",
            ),
        ]
    )
    sf["artifacts"] = artifacts

    bindings = [
        binding(
            "check_pcd_sftp_folder",
            "file_location_availability_sensor",
            [("file_location_resource", "pcd_sftp_resource")],
            [
                ("availability_decision", "check_pcd_sftp_folder_decision"),
                ("check_status", "check_pcd_sftp_folder_status"),
            ],
            {
                "location_type": "sftp",
                "path": "/data/pcd",
                "availability_condition": "contains_matching_files",
                "filename_pattern": "*.csv",
            },
            "Checks the exact SFTP drop-zone condition before the shared-folder check.",
        ),
        binding(
            "check_pcd_shared_folder",
            "file_location_availability_sensor",
            [("file_location_resource", "pcd_shared_folder_resource")],
            [
                ("availability_decision", "check_pcd_shared_folder_decision"),
                ("check_status", "check_pcd_shared_folder_status"),
            ],
            {
                "location_type": "filesystem",
                "path": "/data/pcd",
                "availability_condition": "contains_matching_files",
                "filename_pattern": "*.csv",
            },
            "Checks the exact shared-folder condition before the extraction phases.",
        ),
    ]
    for intent_id in api_intents:
        bindings.append(
            binding(
                intent_id,
                "http_api_request_artifact_extractor",
                [("http_api_resource", "pcd_api_resource")],
                [
                    ("response_artifact", f"{intent_id}_result"),
                    ("extraction_status", f"{intent_id}_status"),
                ],
                {
                    "endpoint": f"/{intent_id}",
                    "method": "GET",
                    "expected_content_types": ["application/json"],
                    "output_name": f"{intent_id}.json",
                },
                f"Executes the source HTTP request for {intent_id}.",
            )
        )
    bindings.extend(
        [
            binding(
                "pcd_file_upload",
                "kubernetes_job_template_executor",
                [
                    ("kubernetes_cluster", "kubernetes_cluster_resource"),
                    ("job_template", "pcd_job_template"),
                ],
                [
                    ("job_reference", "pcd_file_upload_result"),
                    ("job_status", "pcd_file_upload_status"),
                ],
                {
                    "job_name_prefix": "pcd-file-upload",
                    "namespace": "pcd",
                    "wait_for_completion": True,
                    "expected_success_condition": "Complete",
                },
                "Submits the reviewed PCD processing Job template and waits for success.",
                secrets=[
                    {
                        "secret": "kubernetes_access_credentials",
                        "kubernetes_secret": "pcd-kubernetes-access",
                        "key": "kubeconfig",
                    }
                ],
            ),
            binding(
                "etl_notification",
                "email_notification_sender",
                [("email_service", "email_resource")],
                [("notification_status", "etl_notification_status")],
                {
                    "to": "pcd-operations@example.test",
                    "subject": "PCD ETL completed",
                    "body": "All PCD extraction phases and the processing Job completed.",
                },
                "Sends the final deterministic completion notification.",
            ),
        ]
    )
    sf["bindings"] = bindings

    edges = [
        {"from": "check_pcd_sftp_folder", "to": "check_pcd_shared_folder"},
    ]
    edges.extend({"from": "check_pcd_shared_folder", "to": item} for item in first_phase)
    edges.extend(
        {"from": source, "to": target} for source in first_phase for target in second_phase
    )
    edges.extend({"from": item, "to": "pcd_file_upload"} for item in second_phase)
    edges.append({"from": "pcd_file_upload", "to": "etl_notification"})
    sf["control_flow"] = {
        "edges": edges,
        "parallel_groups": [
            {"group_id": "first_extract_phase", "intent_ids": first_phase},
            {"group_id": "second_extract_phase", "intent_ids": second_phase},
        ],
        "branches": [],
        "gates": [
            {
                "gate_id": "pcd_input_available",
                "sensor_intent": "check_pcd_shared_folder",
                "condition": "available == true",
                "gated_intents": [*first_phase, *second_phase, "pcd_file_upload", "etl_notification"],
            }
        ],
    }
    add_source_accounting(sf, {"Start_PCD_Extract_1", "Start_PCD_Extract_2"})
    rebuild_consumers(sf)
    write_yaml(path, sf)

    tasks = []
    gated = set([*first_phase, *second_phase, "pcd_file_upload", "etl_notification"])
    for intent in sf["service_intents"]:
        intent_id = intent["intent_id"]
        task: dict[str, Any] = {
            "intent_id": intent_id,
            "script": "scripts/01_run.py",
            "arguments": ["--workspace", "{workspace}", "--step", intent_id],
        }
        if intent_id == "check_pcd_sftp_folder":
            task["arguments"].extend(["--available", "{pcd_data_available}"])
        elif intent_id == "check_pcd_shared_folder":
            task["dependencies"] = ["check_pcd_sftp_folder"]
            task["arguments"].extend(["--available", "{pcd_data_available}"])
            task["output_parameters"] = [
                {
                    "name": "available",
                    "path": "/workspace/artifacts/pcd_data_available.txt",
                }
            ]
        elif intent_id in first_phase:
            task["dependencies"] = ["check_pcd_shared_folder"]
        elif intent_id in second_phase:
            task["dependencies"] = first_phase
        elif intent_id == "pcd_file_upload":
            task["dependencies"] = second_phase
        elif intent_id == "etl_notification":
            task["dependencies"] = ["pcd_file_upload"]
        if intent_id in gated:
            task["when"] = (
                "{{tasks.check_pcd_shared_folder.outputs.parameters.available}} == true"
            )
            task["local_condition"] = {
                "path": "artifacts/check_pcd_shared_folder_decision.json",
                "json_path": "available",
                "equals": True,
            }
        tasks.append(task)
    write_yaml(
        instance / "runtime" / "manifest.yaml",
        {
            "runtime_manifest_version": "0.1.0",
            "pipeline_id": "pcd_etl",
            "image": "python:3.12-slim",
            "workflow_parameters": [{"name": "pcd-data-available", "default": True}],
            "tasks": tasks,
            "scenarios": [
                {"name": "pcd_data_available", "parameters": {"pcd_data_available": True}},
                {"name": "pcd_data_missing", "parameters": {"pcd_data_available": False}},
            ],
            "cron": {"schedule": "0 0 * * *", "timezone": "UTC"},
        },
    )
    write_yaml(
        instance / "gold" / "assertions.yaml",
        {
            "assertions_version": "0.1.0",
            "pipeline_id": "pcd_etl",
            "scenarios": [
                {
                    "scenario": "pcd_data_available",
                    "assertions": [
                        {
                            "assertion_id": "sftp_ready",
                            "type": "json_path_equals",
                            "path": "artifacts/check_pcd_sftp_folder_decision.json",
                            "json_path": "available",
                            "expected": True,
                        },
                        {
                            "assertion_id": "shared_folder_ready",
                            "type": "json_path_equals",
                            "path": "artifacts/check_pcd_shared_folder_decision.json",
                            "json_path": "available",
                            "expected": True,
                        },
                        {
                            "assertion_id": "first_phase_extracted",
                            "type": "json_path_equals",
                            "path": "artifacts/financial_expense_result.json",
                            "json_path": "record_count",
                            "expected": 2,
                        },
                        {
                            "assertion_id": "second_phase_extracted",
                            "type": "json_path_equals",
                            "path": "artifacts/provincial_risk_tracking_result.json",
                            "json_path": "record_count",
                            "expected": 2,
                        },
                        {
                            "assertion_id": "processing_job_completed",
                            "type": "json_path_equals",
                            "path": "artifacts/pcd_file_upload_status.json",
                            "json_path": "success",
                            "expected": True,
                        },
                        {
                            "assertion_id": "completion_email_sent",
                            "type": "json_path_equals",
                            "path": "artifacts/etl_notification_status.json",
                            "json_path": "sent",
                            "expected": True,
                        },
                    ],
                },
                {
                    "scenario": "pcd_data_missing",
                    "assertions": [
                        {
                            "assertion_id": "shared_folder_not_ready",
                            "type": "json_path_equals",
                            "path": "artifacts/check_pcd_shared_folder_decision.json",
                            "json_path": "available",
                            "expected": False,
                        },
                        {
                            "assertion_id": "first_phase_skipped",
                            "type": "file_absent",
                            "path": "artifacts/financial_expense_result.json",
                        },
                        {
                            "assertion_id": "second_phase_skipped",
                            "type": "file_absent",
                            "path": "artifacts/provincial_risk_tracking_result.json",
                        },
                        {
                            "assertion_id": "processing_job_skipped",
                            "type": "file_absent",
                            "path": "artifacts/pcd_file_upload_status.json",
                        },
                        {
                            "assertion_id": "notification_skipped",
                            "type": "file_absent",
                            "path": "artifacts/etl_notification_status.json",
                        },
                    ],
                },
            ],
        },
    )
    contracts = instance / "contracts" / "artifacts"
    write_json(contracts / "st.schema.json", status_schema())
    write_json(
        contracts / "availability.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["available", "success"],
            "properties": {
                "available": {"type": "boolean"},
                "success": {"const": True},
            },
        },
    )
    write_json(
        contracts / "api_result.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["dataset", "record_count", "records"],
            "properties": {
                "dataset": {"type": "string"},
                "record_count": {"type": "integer", "minimum": 0},
                "records": {"type": "array"},
            },
        },
    )
    write_json(
        contracts / "job_reference.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["job_name", "namespace"],
            "properties": {
                "job_name": {"type": "string"},
                "namespace": {"type": "string"},
            },
        },
    )
    write_json(
        contracts / "notification.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["sent", "success"],
            "properties": {
                "sent": {"const": True},
                "success": {"const": True},
            },
        },
    )


def harden_mondo() -> None:
    instance = INSTANCES / "etl_import_mondo"
    path = instance / "gold" / "serviceflow.yaml"
    sf = load_yaml(path)
    sf["external_systems"] = [
        {
            "system_id": "github_releases",
            "type": "http_api",
            "name": "GitHub Mondo releases",
            "identifier": "https://github.com/monarch-initiative/mondo/releases",
            "access_mode": "read",
            "authentication": "none",
            "mock_strategy": "fixture",
        },
        {
            "system_id": "object_storage",
            "type": "object_storage",
            "name": "Mondo data lake",
            "identifier": "s3://cqgc-app-datalake",
            "access_mode": "read_write",
            "authentication": "secret",
            "mock_strategy": "fixture",
        },
        {
            "system_id": "spark_execution",
            "type": "cloud_service",
            "name": "Spark execution context",
            "identifier": "ETL",
            "access_mode": "invoke",
            "authentication": "managed_identity",
            "mock_strategy": "fixture",
        },
        {
            "system_id": "elasticsearch",
            "type": "database",
            "name": "Mondo Elasticsearch cluster",
            "identifier": "mondo",
            "access_mode": "read_write",
            "authentication": "secret",
            "mock_strategy": "fixture",
        },
        {
            "system_id": "slack",
            "type": "messaging",
            "name": "Mondo Slack notifications",
            "identifier": "mondo-etl",
            "access_mode": "invoke",
            "authentication": "secret",
            "mock_strategy": "fixture",
        },
    ]
    configure_intent(
        sf,
        "download_mondo_terms",
        capability="Synchronize a newer Mondo release asset into object storage.",
        inputs=["github_repository", "object_storage_destination"],
        outputs=["mondo_asset", "mondo_asset_metadata", "download_status"],
        external_system_refs=["github_releases", "object_storage"],
        network_access="required",
        secret_access="required",
        rationale="The source discovers a GitHub release, downloads its OBO asset, and stores it in S3.",
        category="Extractor",
    )
    configure_intent(
        sf,
        "normalized_mondo_terms",
        capability="Run the configured Spark class to normalize Mondo object-storage inputs.",
        inputs=[
            "mondo_source_objects",
            "mondo_asset_metadata",
            "object_storage_destination",
            "spark_execution_context",
        ],
        outputs=["normalized_dataset", "normalize_status"],
        external_system_refs=["object_storage", "spark_execution"],
        network_access="required",
        secret_access="required",
        rationale="The source is a Spark object-storage dataset transformation.",
        category="Transformer",
    )
    configure_intent(
        sf,
        "index_mondo_terms",
        capability="Run the configured Spark indexer to load normalized Mondo terms into Elasticsearch.",
        inputs=[
            "normalized_dataset",
            "mondo_index_template",
            "mondo_asset_metadata",
            "elasticsearch_cluster",
            "spark_execution_context",
        ],
        outputs=["mondo_index_reference", "load_status"],
        external_system_refs=["elasticsearch", "spark_execution"],
        network_access="required",
        secret_access="optional",
        rationale="The source explicitly runs a Spark Elasticsearch indexing class.",
        category="Loader",
    )
    configure_intent(
        sf,
        "publish_mondo",
        capability="Promote the indexed Mondo version through the configured Elasticsearch publication mode.",
        inputs=["mondo_index_reference", "mondo_asset_metadata", "elasticsearch_cluster"],
        outputs=["published_mondo_index", "publish_status"],
        external_system_refs=["elasticsearch"],
        network_access="required",
        secret_access="optional",
        rationale="The source publishes the indexed Mondo version; it is not an email step.",
        category="Publisher",
    )
    configure_intent(
        sf,
        "slack",
        capability="Send a Slack completion message with the published Mondo index context.",
        inputs=["slack_resource", "published_mondo_index"],
        outputs=["slack_notification_status"],
        external_system_refs=["slack"],
        network_access="required",
        secret_access="optional",
        rationale="The final source step is a Slack notification.",
        category="Notifier",
    )

    st_schema = "contracts/artifacts/st.schema.json"
    sf["artifacts"] = [
        artifact(
            "param_source",
            "Runtime parameters",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/params.json",
            persistence="external",
            kind="external_resource",
        ),
        artifact(
            "validation_decision",
            "Parameter validation decision",
            "decision",
            producer="params_validate",
            role="decision",
            schema_ref="contracts/artifacts/validation.schema.json",
        ),
        artifact(
            "github_repository",
            "GitHub release repository",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/github.json",
            persistence="external",
            kind="external_resource",
        ),
        artifact(
            "object_storage_destination",
            "Object storage destination",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/object_storage.json",
            persistence="external",
            kind="external_resource",
        ),
        artifact(
            "mondo_asset",
            "Downloaded Mondo OBO asset",
            "binary",
            producer="download_mondo_terms",
            media_type="application/octet-stream",
        ),
        artifact(
            "mondo_asset_metadata",
            "Mondo release asset metadata",
            "object",
            producer="download_mondo_terms",
            schema_ref="contracts/artifacts/asset_metadata.schema.json",
        ),
        artifact(
            "download_status",
            "Mondo asset synchronization status",
            "status",
            producer="download_mondo_terms",
            role="status",
            schema_ref=st_schema,
        ),
        artifact(
            "mondo_source_objects",
            "Mondo source object references",
            "array",
            producer=None,
            role="input",
            fixture_ref="fixtures/inputs/source_objects.json",
            persistence="external",
        ),
        artifact(
            "spark_execution_context",
            "Spark execution context",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/spark.json",
            persistence="external",
            kind="external_resource",
        ),
        artifact(
            "normalized_dataset",
            "Normalized Mondo dataset",
            "directory",
            producer="normalized_mondo_terms",
            media_type="application/x-directory",
        ),
        artifact(
            "normalize_status",
            "Mondo normalization status",
            "status",
            producer="normalized_mondo_terms",
            role="status",
            schema_ref=st_schema,
        ),
        artifact(
            "mondo_index_template",
            "Mondo Elasticsearch index template",
            "json",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/index_template.json",
            persistence="external",
        ),
        artifact(
            "elasticsearch_cluster",
            "Elasticsearch cluster resource",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/elasticsearch.json",
            persistence="external",
            kind="external_resource",
        ),
        artifact(
            "mondo_index_reference",
            "Loaded Mondo index reference",
            "object",
            producer="index_mondo_terms",
            schema_ref="contracts/artifacts/index_reference.schema.json",
        ),
        artifact(
            "load_status",
            "Mondo index load status",
            "status",
            producer="index_mondo_terms",
            role="status",
            schema_ref=st_schema,
        ),
        artifact(
            "published_mondo_index",
            "Published Mondo index",
            "object",
            producer="publish_mondo",
            schema_ref="contracts/artifacts/published_index.schema.json",
        ),
        artifact(
            "publish_status",
            "Mondo publish status",
            "status",
            producer="publish_mondo",
            role="status",
            schema_ref=st_schema,
        ),
        artifact(
            "slack_resource",
            "Slack service resource",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/slack.json",
            persistence="external",
            kind="external_resource",
        ),
        artifact(
            "slack_notification_status",
            "Slack notification status",
            "notification",
            producer="slack",
            role="status",
            schema_ref="contracts/artifacts/notification.schema.json",
        ),
    ]
    sf["bindings"] = [
        binding(
            "params_validate",
            "runtime_parameter_allowed_values_validator",
            [("runtime_parameters", "param_source")],
            [("validation_decision", "validation_decision")],
            {
                "validation_rules": {
                    "required": ["color"],
                    "allowed_values": {"color": ["blue", "green"]},
                }
            },
            "Validates the publication color before any remote work.",
        ),
        binding(
            "download_mondo_terms",
            "github_release_asset_object_storage_sync",
            [
                ("github_release_repository", "github_repository"),
                ("object_storage_destination", "object_storage_destination"),
            ],
            [
                ("downloaded_asset", "mondo_asset"),
                ("asset_metadata", "mondo_asset_metadata"),
                ("sync_status", "download_status"),
            ],
            {
                "repository_owner": "monarch-initiative",
                "repository_name": "mondo",
                "release_selector": "latest",
                "asset_name_pattern": "mondo-base.obo",
                "destination_prefix": "raw/landing/mondo",
                "skip_if_current": True,
            },
            "Synchronizes the latest reviewed Mondo OBO release asset into the data lake.",
        ),
        binding(
            "normalized_mondo_terms",
            "spark_class_object_storage_dataset_transformer",
            [
                ("source_objects", "mondo_source_objects"),
                ("version_metadata", "mondo_asset_metadata"),
                ("object_storage", "object_storage_destination"),
                ("spark_execution_context", "spark_execution_context"),
            ],
            [
                ("output_dataset", "normalized_dataset"),
                ("transform_status", "normalize_status"),
            ],
            {
                "spark_class": "bio.ferlab.HPOMain",
                "spark_config": "config-etl-medium",
                "output_uri": "public/mondo_terms",
                "app_name": "mondo-normalization",
                "application_args": {"exclude_root": "MONDO:0700096"},
            },
            "Runs the source Spark normalization class with the reviewed exclusion rule.",
        ),
        binding(
            "index_mondo_terms",
            "spark_elasticsearch_index_loader",
            [
                ("source_dataset", "normalized_dataset"),
                ("index_template", "mondo_index_template"),
                ("version_metadata", "mondo_asset_metadata"),
                ("elasticsearch_cluster", "elasticsearch_cluster"),
                ("spark_execution_context", "spark_execution_context"),
            ],
            [
                ("index_reference", "mondo_index_reference"),
                ("index_load_status", "load_status"),
            ],
            {
                "spark_class": "bio.ferlab.clin.etl.es.Indexer",
                "spark_config": "config-etl-singleton",
                "index_name": "mondo",
                "index_type": "mondo_terms",
                "config_file": "config/test.conf",
                "write_mode": "replace",
            },
            "Loads the normalized directory through the reviewed Spark Elasticsearch indexer.",
        ),
        binding(
            "publish_mondo",
            "elasticsearch_index_publisher",
            [
                ("index_reference", "mondo_index_reference"),
                ("version_metadata", "mondo_asset_metadata"),
                ("elasticsearch_cluster", "elasticsearch_cluster"),
            ],
            [
                ("published_index", "published_mondo_index"),
                ("publish_status", "publish_status"),
            ],
            {
                "publication_mode": "color_slot",
                "alias_name": "mondo",
                "color": "blue",
            },
            "Promotes the loaded index through the requested blue/green publication slot.",
        ),
        binding(
            "slack",
            "slack_notification_sender",
            [
                ("slack_service", "slack_resource"),
                ("message_context", "published_mondo_index"),
            ],
            [("notification_status", "slack_notification_status")],
            {
                "channel": "#mondo-etl",
                "message_template": "Mondo index {index_name} version {version} published.",
                "username": "prompt2serviceflow",
            },
            "Sends a completion message grounded in the published index artifact.",
        ),
    ]
    add_source_accounting(sf)
    rebuild_consumers(sf)
    write_yaml(path, sf)

    gated = {
        "normalized_mondo_terms",
        "index_mondo_terms",
        "publish_mondo",
        "slack",
    }
    dependencies = {
        "download_mondo_terms": ["params_validate"],
        "normalized_mondo_terms": ["download_mondo_terms"],
        "index_mondo_terms": ["normalized_mondo_terms"],
        "publish_mondo": ["index_mondo_terms"],
        "slack": ["publish_mondo"],
    }
    tasks = []
    for intent in sf["service_intents"]:
        intent_id = intent["intent_id"]
        step = {
            "params_validate": "validate",
            "download_mondo_terms": "download",
            "normalized_mondo_terms": "normalize",
            "index_mondo_terms": "index",
            "publish_mondo": "publish",
            "slack": "slack",
        }[intent_id]
        task: dict[str, Any] = {
            "intent_id": intent_id,
            "script": "scripts/01_run.py",
            "arguments": ["--workspace", "{workspace}", "--step", step],
        }
        if intent_id in dependencies:
            task["dependencies"] = dependencies[intent_id]
        if intent_id == "download_mondo_terms":
            task["arguments"].extend(["--new-release", "{new_release}"])
            task["output_parameters"] = [
                {
                    "name": "updated",
                    "path": "/workspace/artifacts/mondo_asset_updated.txt",
                }
            ]
        if intent_id in gated:
            task["when"] = "{{tasks.download_mondo_terms.outputs.parameters.updated}} == true"
            task["local_condition"] = {
                "path": "artifacts/download_status.json",
                "json_path": "updated",
                "equals": True,
            }
        tasks.append(task)
    write_yaml(
        instance / "runtime" / "manifest.yaml",
        {
            "runtime_manifest_version": "0.1.0",
            "pipeline_id": "etl_import_mondo",
            "image": "python:3.12-slim",
            "workflow_parameters": [{"name": "new-release", "default": True}],
            "tasks": tasks,
            "scenarios": [
                {"name": "new_release", "parameters": {"new_release": True}},
                {"name": "already_current", "parameters": {"new_release": False}},
            ],
        },
    )
    write_yaml(
        instance / "gold" / "assertions.yaml",
        {
            "assertions_version": "0.1.0",
            "pipeline_id": "etl_import_mondo",
            "scenarios": [
                {
                    "scenario": "new_release",
                    "assertions": [
                        {
                            "assertion_id": "parameters_valid",
                            "type": "json_path_equals",
                            "path": "artifacts/validation_decision.json",
                            "json_path": "valid",
                            "expected": True,
                        },
                        {
                            "assertion_id": "asset_updated",
                            "type": "json_path_equals",
                            "path": "artifacts/download_status.json",
                            "json_path": "updated",
                            "expected": True,
                        },
                        {
                            "assertion_id": "normalized_dataset_created",
                            "type": "file_exists",
                            "path": "artifacts/normalized_dataset/manifest.json",
                        },
                        {
                            "assertion_id": "index_loaded",
                            "type": "json_path_equals",
                            "path": "artifacts/mondo_index_reference.json",
                            "json_path": "index_name",
                            "expected": "mondo-v2026-01",
                        },
                        {
                            "assertion_id": "index_published",
                            "type": "json_path_equals",
                            "path": "artifacts/published_mondo_index.json",
                            "json_path": "alias",
                            "expected": "mondo",
                        },
                        {
                            "assertion_id": "slack_sent",
                            "type": "json_path_equals",
                            "path": "artifacts/slack_notification_status.json",
                            "json_path": "sent",
                            "expected": True,
                        },
                    ],
                },
                {
                    "scenario": "already_current",
                    "assertions": [
                        {
                            "assertion_id": "asset_not_updated",
                            "type": "json_path_equals",
                            "path": "artifacts/download_status.json",
                            "json_path": "updated",
                            "expected": False,
                        },
                        {
                            "assertion_id": "normalization_skipped",
                            "type": "file_absent",
                            "path": "artifacts/normalize_status.json",
                        },
                        {
                            "assertion_id": "indexing_skipped",
                            "type": "file_absent",
                            "path": "artifacts/load_status.json",
                        },
                        {
                            "assertion_id": "publication_skipped",
                            "type": "file_absent",
                            "path": "artifacts/publish_status.json",
                        },
                        {
                            "assertion_id": "notification_skipped",
                            "type": "file_absent",
                            "path": "artifacts/slack_notification_status.json",
                        },
                    ],
                },
            ],
        },
    )
    contracts = instance / "contracts" / "artifacts"
    write_json(contracts / "st.schema.json", status_schema())
    for filename, required, properties in [
        (
            "validation.schema.json",
            ["valid", "success"],
            {"valid": {"type": "boolean"}, "success": {"const": True}},
        ),
        (
            "asset_metadata.schema.json",
            ["asset_name", "version", "object_uri"],
            {
                "asset_name": {"type": "string"},
                "version": {"type": "string"},
                "object_uri": {"type": "string"},
            },
        ),
        (
            "index_reference.schema.json",
            ["index_name", "document_count"],
            {
                "index_name": {"type": "string"},
                "document_count": {"type": "integer", "minimum": 0},
            },
        ),
        (
            "published_index.schema.json",
            ["index_name", "alias", "version"],
            {
                "index_name": {"type": "string"},
                "alias": {"type": "string"},
                "version": {"type": "string"},
            },
        ),
        (
            "notification.schema.json",
            ["sent", "success"],
            {"sent": {"const": True}, "success": {"const": True}},
        ),
    ]:
        write_json(
            contracts / filename,
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": required,
                "properties": properties,
            },
        )


def harden_wf_main() -> None:
    instance = INSTANCES / "wf_main_datasets_load_l2_to_l2"
    path = instance / "gold" / "serviceflow.yaml"
    sf = load_yaml(path)
    remove_intents(sf, {"email_on_failure"})
    sf["external_systems"] = [
        {
            "system_id": "dwh_database",
            "type": "database",
            "name": "DWH database",
            "identifier": "dwh",
            "access_mode": "read_write",
            "authentication": "secret",
            "mock_strategy": "fixture",
        },
        {
            "system_id": "workflow_orchestrator",
            "type": "external_workflow",
            "name": "Airflow workflow orchestrator",
            "identifier": "airflow",
            "access_mode": "invoke",
            "authentication": "secret",
            "mock_strategy": "fixture",
        },
        {
            "system_id": "sap_api",
            "type": "http_api",
            "name": "SAP completion API",
            "identifier": "sap_conn",
            "access_mode": "write",
            "authentication": "secret",
            "mock_strategy": "fixture",
        },
    ]
    configure_intent(
        sf,
        "end",
        capability="Finalize the workflow session metadata with successful status.",
        inputs=["metadata_db", "load_id"],
        outputs=["final_session_ref", "end_status"],
        external_system_refs=["dwh_database"],
        network_access="required",
        secret_access="required",
        rationale="The source end step finalizes the same registered workflow session.",
        category="Loader",
    )
    configure_intent(
        sf,
        "wait_for_l2_full_load",
        capability="Run the configured read-only DWH flag query and emit readiness.",
        inputs=["dwh_database_resource"],
        outputs=["l2_decision", "l2_status"],
        external_system_refs=["dwh_database"],
        network_access="required",
        secret_access="required",
        rationale="The source is an SQL readiness sensor, not an external workflow sensor.",
        category="Sensor",
    )
    configure_intent(
        sf,
        "wait_for_success_end",
        capability="Check whether the previous workflow end task completed successfully.",
        inputs=["ext_wf_resource"],
        outputs=["success_decision"],
        external_system_refs=["workflow_orchestrator"],
        network_access="required",
        secret_access="required",
        rationale="The source targets a specific external workflow task and logical execution.",
        category="Sensor",
    )
    configure_intent(
        sf,
        "send_flg_to_sap",
        capability="Read the segmentation table and publish a completion flag to SAP.",
        inputs=["dwh_database_resource", "segmentation_source_table", "sap_resource"],
        outputs=["flag_status", "sap_request_summary"],
        external_system_refs=["dwh_database", "sap_api"],
        network_access="required",
        secret_access="required",
        rationale="The source reads a DWH table and invokes the SAP HTTP endpoint.",
        category="Publisher",
    )
    for intent_id in [
        "run_sys_kill_all_session_pg",
        "run_wf_data_preparation_for_reports",
        "load_ds_client_segmentation",
    ]:
        configure_intent(
            sf,
            intent_id,
            capability=f"Trigger and wait for external workflow {intent_id}.",
            inputs=["ext_wf_resource"],
            outputs=[
                {
                    "run_sys_kill_all_session_pg": "kill_result",
                    "run_wf_data_preparation_for_reports": "dataprep_result",
                    "load_ds_client_segmentation": "segment_result",
                }[intent_id],
                {
                    "run_sys_kill_all_session_pg": "kill_status",
                    "run_wf_data_preparation_for_reports": "dataprep_status",
                    "load_ds_client_segmentation": "segment_status",
                }[intent_id],
            ],
            external_system_refs=["workflow_orchestrator"],
            network_access="required",
            secret_access="required",
            rationale="The source explicitly triggers an external workflow and waits for completion.",
            category="ExternalWorkflowAdapter",
        )

    st_schema = "contracts/artifacts/st.schema.json"
    sf["artifacts"] = [
        artifact(
            "dwh_database_resource",
            "DWH database resource",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/db.json",
            persistence="external",
            sensitivity="confidential",
            kind="external_resource",
        ),
        artifact(
            "metadata_db",
            "Workflow metadata database",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/db.json",
            persistence="external",
            sensitivity="confidential",
            kind="external_resource",
        ),
        artifact(
            "ext_wf_resource",
            "External workflow orchestrator",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/ext_wf.json",
            persistence="external",
            sensitivity="confidential",
            kind="external_resource",
        ),
        artifact(
            "sap_resource",
            "SAP HTTP API resource",
            "object",
            producer=None,
            role="config",
            fixture_ref="fixtures/inputs/sap.json",
            persistence="external",
            sensitivity="confidential",
            kind="external_resource",
        ),
        artifact(
            "segmentation_source_table",
            "Client segmentation source table",
            "table",
            producer=None,
            role="input",
            fixture_ref="fixtures/inputs/segmentation_table.json",
            persistence="external",
        ),
        artifact(
            "l2_decision",
            "L2 load readiness decision",
            "decision",
            producer="wait_for_l2_full_load",
            role="decision",
            schema_ref="contracts/artifacts/readiness.schema.json",
        ),
        artifact(
            "l2_status",
            "L2 load query status",
            "status",
            producer="wait_for_l2_full_load",
            role="status",
            schema_ref=st_schema,
        ),
        artifact(
            "load_id",
            "Workflow load ID",
            "string",
            producer="get_load_id",
            media_type="text/plain",
        ),
        artifact(
            "gen_status",
            "Load ID generation status",
            "status",
            producer="get_load_id",
            role="status",
            schema_ref=st_schema,
        ),
        artifact(
            "session_ref",
            "Registered workflow session",
            "object",
            producer="workflow_registration",
            schema_ref="contracts/artifacts/session.schema.json",
        ),
        artifact(
            "reg_status",
            "Workflow registration status",
            "status",
            producer="workflow_registration",
            role="status",
            schema_ref=st_schema,
        ),
        artifact(
            "success_decision",
            "Previous workflow task completion decision",
            "decision",
            producer="wait_for_success_end",
            role="decision",
            schema_ref="contracts/artifacts/completion.schema.json",
        ),
        artifact(
            "kill_result",
            "Session cleanup workflow run",
            "object",
            producer="run_sys_kill_all_session_pg",
            schema_ref="contracts/artifacts/run_reference.schema.json",
        ),
        artifact(
            "kill_status",
            "Session cleanup trigger status",
            "status",
            producer="run_sys_kill_all_session_pg",
            role="status",
            schema_ref=st_schema,
        ),
        artifact(
            "dataprep_result",
            "Data preparation workflow run",
            "object",
            producer="run_wf_data_preparation_for_reports",
            schema_ref="contracts/artifacts/run_reference.schema.json",
        ),
        artifact(
            "dataprep_status",
            "Data preparation trigger status",
            "status",
            producer="run_wf_data_preparation_for_reports",
            role="status",
            schema_ref=st_schema,
        ),
        artifact(
            "segment_result",
            "Segmentation workflow run",
            "object",
            producer="load_ds_client_segmentation",
            schema_ref="contracts/artifacts/run_reference.schema.json",
        ),
        artifact(
            "segment_status",
            "Segmentation trigger status",
            "status",
            producer="load_ds_client_segmentation",
            role="status",
            schema_ref=st_schema,
        ),
        artifact(
            "flag_status",
            "SAP publication status",
            "status",
            producer="send_flg_to_sap",
            role="status",
            schema_ref=st_schema,
        ),
        artifact(
            "sap_request_summary",
            "SAP request summary",
            "object",
            producer="send_flg_to_sap",
            schema_ref="contracts/artifacts/request_summary.schema.json",
        ),
        artifact(
            "final_session_ref",
            "Finalized workflow session",
            "object",
            producer="end",
            schema_ref="contracts/artifacts/session.schema.json",
        ),
        artifact(
            "end_status",
            "Workflow finalization status",
            "status",
            producer="end",
            role="status",
            schema_ref=st_schema,
        ),
    ]
    sf["bindings"] = [
        binding(
            "wait_for_l2_full_load",
            "sql_query_readiness_sensor",
            [("database", "dwh_database_resource")],
            [
                ("readiness_decision", "l2_decision"),
                ("query_status", "l2_status"),
            ],
            {
                "sql_query": (
                    "select * from md.dwh_flag where flag_cd = "
                    "'l1_to_l2_load_successfull' and bussines_date = current_date - 1"
                ),
                "success_condition": "row_exists",
                "expected_row_count": 1,
            },
            "Evaluates the exact DWH readiness flag query from the source.",
        ),
        binding(
            "get_load_id",
            "workflow_load_id_generator",
            [],
            [("load_id", "load_id"), ("generation_status", "gen_status")],
            {"generation_strategy": "runtime_context", "prefix": "wf-l2-"},
            "Generates a deterministic load identifier from the supplied run label.",
        ),
        binding(
            "workflow_registration",
            "workflow_session_metadata_recorder",
            [("metadata_database", "metadata_db"), ("load_id", "load_id")],
            [
                ("session_record_reference", "session_ref"),
                ("metadata_write_status", "reg_status"),
            ],
            {
                "workflow_id": "WF_MAIN_DATASETS_LOAD_L2_TO_L2",
                "operation": "register",
                "session_status": "running",
                "metadata_target": "workflow_sessions",
            },
            "Registers the generated load ID before downstream workflow execution.",
        ),
        binding(
            "wait_for_success_end",
            "external_workflow_task_completion_sensor",
            [("workflow_orchestrator", "ext_wf_resource")],
            [("completion_decision", "success_decision")],
            {
                "external_workflow_id": "WF_MAIN_DATASETS_LOAD_L2_TO_L2",
                "external_step_id": "end",
                "execution_selector": {"logical_date_offset_days": -1},
                "terminal_states": ["success", "failed"],
                "success_states": ["success"],
            },
            "Checks the previous logical execution's end task, as required by the source.",
        ),
    ]
    for intent_id, target, result_id, status_id in [
        (
            "run_sys_kill_all_session_pg",
            "sys_kill_all_session_pg",
            "kill_result",
            "kill_status",
        ),
        (
            "run_wf_data_preparation_for_reports",
            "wf_data_preparation_for_reports",
            "dataprep_result",
            "dataprep_status",
        ),
        (
            "load_ds_client_segmentation",
            "l1_to_l2_p_load_data_ds_client_segmentation_full",
            "segment_result",
            "segment_status",
        ),
    ]:
        sf["bindings"].append(
            binding(
                intent_id,
                "external_workflow_run_trigger",
                [("workflow_orchestrator", "ext_wf_resource")],
                [("run_reference", result_id), ("trigger_status", status_id)],
                {
                    "target_workflow_id": target,
                    "wait_for_completion": True,
                    "run_config": {},
                    "success_states": ["success"],
                },
                f"Triggers and waits for external workflow {target}.",
            )
        )
    sf["bindings"].extend(
        [
            binding(
                "send_flg_to_sap",
                "database_table_http_flag_publisher",
                [
                    ("source_database", "dwh_database_resource"),
                    ("source_table", "segmentation_source_table"),
                    ("http_api_resource", "sap_resource"),
                ],
                [
                    ("publish_status", "flag_status"),
                    ("request_summary", "sap_request_summary"),
                ],
                {
                    "source_table_name": "wk_export.ds_client_segmentation_last_v",
                    "endpoint": "/dwh/load-complete",
                    "method": "POST",
                    "payload_template": {"status": "complete", "row_count": "{row_count}"},
                    "success_status_codes": [200, 202],
                },
                "Publishes the segmentation completion flag using the DWH table and SAP API.",
            ),
            binding(
                "end",
                "workflow_session_metadata_recorder",
                [("metadata_database", "metadata_db"), ("load_id", "load_id")],
                [
                    ("session_record_reference", "final_session_ref"),
                    ("metadata_write_status", "end_status"),
                ],
                {
                    "workflow_id": "WF_MAIN_DATASETS_LOAD_L2_TO_L2",
                    "operation": "finalize",
                    "session_status": "success",
                    "metadata_target": "workflow_sessions",
                },
                "Finalizes the registered workflow session after both downstream branches complete.",
            ),
        ]
    )
    sf["control_flow"] = {
        "edges": [
            {"from": "wait_for_l2_full_load", "to": "get_load_id"},
            {"from": "get_load_id", "to": "workflow_registration"},
            {"from": "workflow_registration", "to": "wait_for_success_end"},
            {"from": "wait_for_success_end", "to": "run_sys_kill_all_session_pg"},
            {
                "from": "run_sys_kill_all_session_pg",
                "to": "run_wf_data_preparation_for_reports",
            },
            {
                "from": "run_sys_kill_all_session_pg",
                "to": "load_ds_client_segmentation",
            },
            {"from": "load_ds_client_segmentation", "to": "send_flg_to_sap"},
            {"from": "run_wf_data_preparation_for_reports", "to": "end"},
            {"from": "send_flg_to_sap", "to": "end"},
        ],
        "parallel_groups": [
            {
                "group_id": "downstream_workflows",
                "intent_ids": [
                    "run_wf_data_preparation_for_reports",
                    "load_ds_client_segmentation",
                ],
            }
        ],
        "branches": [],
        "gates": [
            {
                "gate_id": "l2_load_ready",
                "sensor_intent": "wait_for_l2_full_load",
                "condition": "ready == true",
                "gated_intents": [
                    "get_load_id",
                    "workflow_registration",
                    "wait_for_success_end",
                    "run_sys_kill_all_session_pg",
                    "run_wf_data_preparation_for_reports",
                    "load_ds_client_segmentation",
                    "send_flg_to_sap",
                    "end",
                ],
            }
        ],
    }
    add_source_accounting(sf, {"email_on_failure"})
    rebuild_consumers(sf)
    write_yaml(path, sf)

    dependencies = {
        "get_load_id": ["wait_for_l2_full_load"],
        "workflow_registration": ["get_load_id"],
        "wait_for_success_end": ["workflow_registration"],
        "run_sys_kill_all_session_pg": ["wait_for_success_end"],
        "run_wf_data_preparation_for_reports": ["run_sys_kill_all_session_pg"],
        "load_ds_client_segmentation": ["run_sys_kill_all_session_pg"],
        "send_flg_to_sap": ["load_ds_client_segmentation"],
        "end": ["run_wf_data_preparation_for_reports", "send_flg_to_sap"],
    }
    gated = set(dependencies)
    step_names = {
        "wait_for_l2_full_load": "wait_l2",
        "get_load_id": "load_id",
        "workflow_registration": "register",
        "wait_for_success_end": "wait_success",
        "run_sys_kill_all_session_pg": "kill",
        "run_wf_data_preparation_for_reports": "dataprep",
        "load_ds_client_segmentation": "segment",
        "send_flg_to_sap": "flag",
        "end": "end",
    }
    tasks = []
    ordered_ids = [
        "wait_for_l2_full_load",
        "get_load_id",
        "workflow_registration",
        "wait_for_success_end",
        "run_sys_kill_all_session_pg",
        "run_wf_data_preparation_for_reports",
        "load_ds_client_segmentation",
        "send_flg_to_sap",
        "end",
    ]
    for intent_id in ordered_ids:
        task: dict[str, Any] = {
            "intent_id": intent_id,
            "script": "scripts/01_run.py",
            "arguments": ["--workspace", "{workspace}", "--step", step_names[intent_id]],
        }
        if intent_id in dependencies:
            task["dependencies"] = dependencies[intent_id]
        if intent_id == "wait_for_l2_full_load":
            task["arguments"].extend(["--l2-ready", "{l2_ready}"])
            task["output_parameters"] = [
                {"name": "ready", "path": "/workspace/artifacts/l2_ready.txt"}
            ]
        if intent_id == "get_load_id":
            task["arguments"].extend(["--run-label", "{run_label}"])
        if intent_id in gated:
            task["when"] = "{{tasks.wait_for_l2_full_load.outputs.parameters.ready}} == true"
            task["local_condition"] = {
                "path": "artifacts/l2_decision.json",
                "json_path": "ready",
                "equals": True,
            }
        tasks.append(task)
    write_yaml(
        instance / "runtime" / "manifest.yaml",
        {
            "runtime_manifest_version": "0.1.0",
            "pipeline_id": "wf_main_datasets_load_l2_to_l2",
            "image": "python:3.12-slim",
            "workflow_parameters": [
                {"name": "l2-ready", "default": True},
                {"name": "run-label", "default": "batch-001"},
            ],
            "tasks": tasks,
            "scenarios": [
                {
                    "name": "l2_ready",
                    "parameters": {"l2_ready": True, "run_label": "batch-001"},
                },
                {
                    "name": "l2_not_ready",
                    "parameters": {"l2_ready": False, "run_label": "batch-001"},
                },
            ],
        },
    )
    write_yaml(
        instance / "gold" / "assertions.yaml",
        {
            "assertions_version": "0.1.0",
            "pipeline_id": "wf_main_datasets_load_l2_to_l2",
            "scenarios": [
                {
                    "scenario": "l2_ready",
                    "assertions": [
                        {
                            "assertion_id": "l2_ready",
                            "type": "json_path_equals",
                            "path": "artifacts/l2_decision.json",
                            "json_path": "ready",
                            "expected": True,
                        },
                        {
                            "assertion_id": "load_id_generated",
                            "type": "file_exists",
                            "path": "artifacts/load_id.txt",
                        },
                        {
                            "assertion_id": "previous_run_complete",
                            "type": "json_path_equals",
                            "path": "artifacts/success_decision.json",
                            "json_path": "completed",
                            "expected": True,
                        },
                        {
                            "assertion_id": "data_preparation_triggered",
                            "type": "json_path_equals",
                            "path": "artifacts/dataprep_result.json",
                            "json_path": "workflow_id",
                            "expected": "wf_data_preparation_for_reports",
                        },
                        {
                            "assertion_id": "segmentation_triggered",
                            "type": "json_path_equals",
                            "path": "artifacts/segment_result.json",
                            "json_path": "workflow_id",
                            "expected": "l1_to_l2_p_load_data_ds_client_segmentation_full",
                        },
                        {
                            "assertion_id": "sap_flag_published",
                            "type": "json_path_equals",
                            "path": "artifacts/flag_status.json",
                            "json_path": "success",
                            "expected": True,
                        },
                        {
                            "assertion_id": "session_finalized",
                            "type": "json_path_equals",
                            "path": "artifacts/end_status.json",
                            "json_path": "operation",
                            "expected": "finalize",
                        },
                    ],
                },
                {
                    "scenario": "l2_not_ready",
                    "assertions": [
                        {
                            "assertion_id": "l2_blocked",
                            "type": "json_path_equals",
                            "path": "artifacts/l2_decision.json",
                            "json_path": "ready",
                            "expected": False,
                        },
                        {
                            "assertion_id": "load_id_not_generated",
                            "type": "file_absent",
                            "path": "artifacts/load_id.txt",
                        },
                        {
                            "assertion_id": "sap_not_called",
                            "type": "file_absent",
                            "path": "artifacts/flag_status.json",
                        },
                        {
                            "assertion_id": "session_not_finalized",
                            "type": "file_absent",
                            "path": "artifacts/end_status.json",
                        },
                    ],
                },
            ],
        },
    )
    contracts = instance / "contracts" / "artifacts"
    write_json(contracts / "st.schema.json", status_schema())
    for filename, required, properties in [
        (
            "readiness.schema.json",
            ["ready", "success"],
            {"ready": {"type": "boolean"}, "success": {"const": True}},
        ),
        (
            "completion.schema.json",
            ["completed", "succeeded"],
            {"completed": {"type": "boolean"}, "succeeded": {"type": "boolean"}},
        ),
        (
            "session.schema.json",
            ["load_id", "operation"],
            {"load_id": {"type": "string"}, "operation": {"type": "string"}},
        ),
        (
            "run_reference.schema.json",
            ["workflow_id", "run_id"],
            {"workflow_id": {"type": "string"}, "run_id": {"type": "string"}},
        ),
        (
            "request_summary.schema.json",
            ["endpoint", "method", "row_count"],
            {
                "endpoint": {"type": "string"},
                "method": {"type": "string"},
                "row_count": {"type": "integer", "minimum": 0},
            },
        ),
    ]:
        write_json(
            contracts / filename,
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": required,
                "properties": properties,
            },
        )


def main() -> None:
    harden_airflow_cleanup()
    harden_global_dag()
    harden_pcd_etl()
    harden_mondo()
    harden_wf_main()
    update_manifest_statuses()
    print("semantic hardening batch 01 applied")


if __name__ == "__main__":
    main()
