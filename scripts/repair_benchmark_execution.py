#!/usr/bin/env python3
"""Normalize scenario fixtures, packaging, media samples, and reference assertions."""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import struct
import zlib
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
INSTANCE_ROOT = ROOT / "benchmark" / "instances"


def dump_yaml(path: Path, document: Any) -> None:
    content = yaml.safe_dump(document, sort_keys=False, width=100)
    if not path.is_file() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")


def write_bytes_if_changed(path: Path, content: bytes) -> None:
    if not path.is_file() or path.read_bytes() != content:
        path.write_bytes(content)


def write_json_if_changed(path: Path, document: Any) -> None:
    content = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if not path.is_file() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)


def sample_png(label: str) -> bytes:
    digest = hashlib.sha256(label.encode("utf-8")).digest()
    width = height = 16
    pixel = bytes((digest[0], digest[1], digest[2], 255))
    scanlines = b"".join(b"\x00" + pixel * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(scanlines, 9))
        + png_chunk(b"IEND", b"")
    )


def sample_pdf(label: str) -> bytes:
    safe = label.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 50 740 Td (ServiceComposeBench-ETL sample: {safe}) Tj ET\n".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    document = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(document))
        document.extend(f"{number} 0 obj\n".encode("ascii"))
        document.extend(obj + b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(document)


def scenario_fixture_root(
    instance: Path, scenario: dict[str, Any], *, scenario_count: int
) -> Path:
    conventional = instance / "fixtures" / "scenarios" / scenario["name"]
    if conventional.is_dir():
        return conventional
    available = [
        path for path in (instance / "fixtures" / "scenarios").glob("*") if path.is_dir()
    ]
    if scenario_count == 1 and len(available) == 1:
        return available[0]
    return instance / "fixtures" / "inputs"


def add_media_samples(instance: Path, manifest: dict[str, Any]) -> int:
    source_path = instance / "source" / "source_metadata.yaml"
    source = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    modalities = set(source.get("extension", {}).get("input_modalities", []) or [])
    wanted = modalities & {"pdf", "image"}
    if not wanted:
        return 0
    created = 0
    for scenario in manifest["scenarios"]:
        root = instance / scenario["fixture_root"]
        fixture_path = root / "fixture.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        media = fixture.setdefault("sample_media", {})
        if "pdf" in wanted:
            path = root / "sample_document.pdf"
            write_bytes_if_changed(
                path, sample_pdf(f"{manifest['pipeline_id']}:{scenario['name']}")
            )
            media["pdf"] = path.name
            created += 1
        if "image" in wanted:
            path = root / "sample_image.png"
            write_bytes_if_changed(
                path, sample_png(f"{manifest['pipeline_id']}:{scenario['name']}")
            )
            media["image"] = path.name
            created += 1
        write_json_if_changed(fixture_path, fixture)
    return created


def status_artifact(serviceflow: dict[str, Any], intent_id: str) -> str:
    candidates = [
        item
        for item in serviceflow["artifacts"]
        if item.get("producer") == intent_id and item.get("role") == "status"
    ]
    if not candidates:
        intent = next(item for item in serviceflow["service_intents"] if item["intent_id"] == intent_id)
        candidates = [
            item for item in serviceflow["artifacts"] if item["artifact_id"] in intent["outputs"]
        ]
    return candidates[-1]["artifact_id"]


def strengthen_reference_assertions(instance: Path, manifest: dict[str, Any]) -> bool:
    first_script = instance / "runtime" / manifest["tasks"][0]["script"]
    if "fixture_summary" not in first_script.read_text(encoding="utf-8"):
        return False
    serviceflow = yaml.safe_load((instance / "gold" / "serviceflow.yaml").read_text(encoding="utf-8"))
    first_intent = manifest["tasks"][0]["intent_id"]
    final_intent = manifest["tasks"][-1]["intent_id"]
    first_status = status_artifact(serviceflow, first_intent)
    final_status = status_artifact(serviceflow, final_intent)
    scenarios = []
    for scenario in manifest["scenarios"]:
        assertions = [
            {
                "assertion_id": "source_fixture_loaded",
                "type": "json_path_equals",
                "path": f"artifacts/{first_status}.json",
                "json_path": "success",
                "expected": True,
            },
            {
                "assertion_id": "source_files_present",
                "type": "json_path_gte",
                "path": f"artifacts/{first_status}.json",
                "json_path": "fixture.file_count",
                "minimum": 1,
            },
            {
                "assertion_id": "source_records_present",
                "type": "json_path_gte",
                "path": f"artifacts/{first_status}.json",
                "json_path": "fixture.record_count",
                "minimum": 1,
            },
            {
                "assertion_id": "final_status_succeeds",
                "type": "json_path_equals",
                "path": f"artifacts/{final_status}.json",
                "json_path": "success",
                "expected": True,
            },
            {
                "assertion_id": "final_artifact_exists",
                "type": "file_exists",
                "path": f"artifacts/{final_status}.json",
            },
        ]
        if len(manifest["tasks"]) > 1:
            assertions.append(
                {
                    "assertion_id": "upstream_evidence_propagated",
                    "type": "json_path_gte",
                    "path": f"artifacts/{final_status}.json",
                    "json_path": "upstream_artifact_count",
                    "minimum": 1,
                }
            )
        scenarios.append({"scenario": scenario["name"], "assertions": assertions})
    dump_yaml(
        instance / "gold" / "assertions.yaml",
        {
            "assertions_version": "0.1.0",
            "pipeline_id": manifest["pipeline_id"],
            "scenarios": scenarios,
        },
    )
    return True


def ensure_packaging(instance: Path, manifest: dict[str, Any]) -> int:
    created = 0
    if not (instance / "Dockerfile").exists():
        label = manifest["pipeline_id"].replace("_", "-")
        (instance / "Dockerfile").write_text(
            "FROM python:3.12-slim\n"
            f'LABEL pipeline="{label}"\n'
            'LABEL benchmark="servicecomposebench-etl"\n'
            "WORKDIR /app\nCOPY runtime/scripts/ /app/scripts/\n"
            "RUN mkdir -p /workspace/artifacts\nENTRYPOINT [\"python\"]\nCMD [\"--help\"]\n",
            encoding="utf-8",
        )
        created += 1
    if not (instance / "pyproject.toml").exists():
        name = manifest["pipeline_id"].replace("_", "-")
        (instance / "pyproject.toml").write_text(
            "[project]\n"
            f'name = "{name}"\nversion = "0.1.0"\n'
            'description = "Deterministic ServiceComposeBench-ETL reference runtime."\n'
            'requires-python = ">=3.12"\ndependencies = []\n\n'
            "[build-system]\nrequires = [\"uv>=0.6\"]\nbuild-backend = \"uv\"\n\n"
            "[tool.uv]\npackage = false\n",
            encoding="utf-8",
        )
        created += 1
    return created


def normalize_status_schema(instance: Path) -> bool:
    path = instance / "contracts" / "artifacts" / "status.schema.json"
    if not path.is_file():
        return False
    document = json.loads(path.read_text(encoding="utf-8"))
    errors = document.get("properties", {}).get("errors")
    if not isinstance(errors, dict) or errors.get("type") != "array":
        return False
    expected_items = {"oneOf": [{"type": "string"}, {"type": "object"}]}
    if errors.get("items") == expected_items:
        return False
    errors["items"] = expected_items
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return True


def remove_unreferenced_generated_scripts(
    instance: Path, manifest: dict[str, Any]
) -> int:
    if instance.parent.name == "main":
        return 0
    referenced = {Path(task["script"]).name for task in manifest["tasks"]}
    removed = 0
    for path in sorted((instance / "runtime" / "scripts").glob("*.py")):
        if path.name in referenced:
            continue
        path.unlink()
        removed += 1
    return removed


def repair_instance(instance: Path) -> tuple[int, int, bool, bool, int]:
    manifest_path = instance / "runtime" / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    for scenario in manifest["scenarios"]:
        root = scenario_fixture_root(
            instance, scenario, scenario_count=len(manifest["scenarios"])
        )
        scenario["fixture_root"] = root.relative_to(instance).as_posix()
        if instance.parent.name != "main" and not (root / "fixture.json").is_file():
            raise ValueError(f"{instance}: scenario {scenario['name']} lacks fixture.json")
    dump_yaml(manifest_path, manifest)
    media_count = add_media_samples(instance, manifest)
    strengthened = strengthen_reference_assertions(instance, manifest)
    packaging_count = ensure_packaging(instance, manifest)
    schema_updated = normalize_status_schema(instance)
    removed_scripts = remove_unreferenced_generated_scripts(instance, manifest)
    return media_count, packaging_count, strengthened, schema_updated, removed_scripts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    media = packaging = strengthened = schemas = removed_scripts = 0
    instances = [
        path
        for path in sorted(INSTANCE_ROOT.glob("*/*"))
        if path.is_dir() and (path / "runtime" / "manifest.yaml").is_file()
    ]
    for instance in instances:
        (
            media_count,
            packaging_count,
            was_strengthened,
            schema_updated,
            removed_count,
        ) = repair_instance(instance)
        media += media_count
        packaging += packaging_count
        strengthened += int(was_strengthened)
        schemas += int(schema_updated)
        removed_scripts += removed_count
    print(
        f"repaired instances={len(instances)} media_files={media} "
        f"packaging_files={packaging} strengthened_assertion_sets={strengthened} "
        f"status_schemas_updated={schemas} removed_unreferenced_scripts={removed_scripts}"
    )


if __name__ == "__main__":
    main()
