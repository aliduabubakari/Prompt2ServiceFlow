#!/usr/bin/env python3
"""Deterministic French government data ETL mock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def boolean(value: str) -> bool:
    return value.lower() in {"1", "true", "yes"}


def write_json(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def write_status(artifacts: Path, step: str, **details: object) -> None:
    write_json(
        artifacts / f"{step}_status.json",
        {"success": True, "errors": [], **details},
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--step", required=True)
    parser.add_argument("--death-records-available", type=boolean, default=True)
    args = parser.parse_args()
    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    step = args.step

    metadata_steps = {
        "ingest_get_nuclear_json": "nuclear",
        "ingest_get_death_resource_list": "deaths",
        "ingest_get_thermal_json": "thermal",
    }
    if step == "ingest_get_city_code_geo":
        write_json(
            artifacts / f"{step}_result.json",
            {"media_type": "text/csv", "artifact": "city_geo_loc.csv"},
        )
        write_status(artifacts, step, http_status=200)
    elif step in metadata_steps:
        dataset = metadata_steps[step]
        write_json(
            artifacts / f"{step}_result.json",
            {
                "dataset_id": dataset,
                "resources": [{"name": f"{dataset}-resource", "format": "csv"}],
            },
        )
        write_status(artifacts, step, http_status=200)
    elif step in {
        "ingest_get_nuclear_data",
        "ingest_get_death_resources",
        "ingest_get_thermal_data",
    }:
        files = {
            "ingest_get_nuclear_data": ["nuclear.csv"],
            "ingest_get_death_resources": ["death-1.txt", "death-2.txt"],
            "ingest_get_thermal_data": ["thermal.csv"],
        }[step]
        write_json(artifacts / f"{step}_result.json", {"files": files})
        write_status(artifacts, step, downloaded=len(files))
    elif step == "stage_import_nuclear_clean_data":
        (artifacts / "nuclear_clean_csv.csv").write_text(
            "plant_name,capacity_mw\nNuclear One,900\n", encoding="utf-8"
        )
        write_status(artifacts, step, rows=1)
    elif step == "stage_import_thermal_clean_data":
        (artifacts / "thermal_clean_csv.csv").write_text(
            "plant_name,capacity_mw\nThermal One,450\n", encoding="utf-8"
        )
        write_status(artifacts, step, rows=1)
    elif step == "stage_create_power_plants_table":
        write_json(
            artifacts / "power_plants_table.json",
            {"tables": ["power_plants"], "row_count": 0},
        )
        write_status(artifacts, step, statement_type="DDL")
    elif step == "stage_create_death_table":
        write_json(
            artifacts / "deaths_table.json",
            {"tables": ["deaths"], "row_count": 0},
        )
        write_status(artifacts, step, statement_type="DDL")
    elif step == "stage_load_data_from_ingestion":
        write_json(
            artifacts / "death_redis_keys.json",
            {"keys": ["death_raw", "imported_death_files"]},
        )
        write_status(artifacts, step, imported_files=2)
    elif step == "stage_cleanse_death_data":
        (artifacts / "death_insert_sql.sql").write_text(
            "INSERT INTO deaths VALUES ('DOE', 'Paris');\n", encoding="utf-8"
        )
        write_status(artifacts, step, statements=1)
    elif step == "stage_death_emptiness_check":
        decision = {
            "has_content": args.death_records_available,
            "success": True,
        }
        write_json(artifacts / "stage_death_emptiness_check_decision.json", decision)
        (artifacts / "death_sql_has_content.txt").write_text(
            str(args.death_records_available).lower(), encoding="utf-8"
        )
        write_status(artifacts, step)
    elif step == "stage_store_deaths_in_postgres":
        write_json(
            artifacts / "stored_deaths_table.json",
            {"tables": ["deaths"], "row_count": 1},
        )
        write_status(artifacts, step, rows=1)
    elif step == "stage_clean_tmp_death_files":
        write_status(artifacts, step, removed_files=3)
    elif step == "stage_clean_tmp_death_redis":
        write_status(artifacts, step, removed_keys=2)
    elif step == "stage_create_plant_persist_sql_query":
        (artifacts / "plant_insert_sql.sql").write_text(
            "INSERT INTO power_plants VALUES ('Plant One', 900);\n",
            encoding="utf-8",
        )
        write_status(artifacts, step, statements=1)
    elif step == "stage_store_plants_in_postgres":
        write_json(
            artifacts / "stored_power_plants_table.json",
            {"tables": ["power_plants"], "row_count": 2},
        )
        write_status(artifacts, step, rows=2)


if __name__ == "__main__":
    main()
