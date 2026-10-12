#!/usr/bin/env python3
"""Detect sensitive fields: identify PII/regulated data in fused supplier records."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace
    artifacts = root / "artifacts"

    fused_data = json.loads((artifacts / "fuse_sources_artifact.json").read_text(encoding="utf-8"))
    reference = json.loads((artifacts / "ingest_reference_source_artifact.json").read_text(encoding="utf-8"))
    patterns = reference["policy"]["sensitive_field_patterns"]

    detected = []
    for s in fused_data["fused_suppliers"]:
        sensitive = {}
        for field, config in patterns.items():
            value = s.get(field, "")
            if value and re.match(config["regex"], value):
                sensitive[field] = {
                    "value": value,
                    "redaction": config["redaction"],
                    "keep_chars": config.get("keep_chars", 0),
                }
        if sensitive:
            detected.append({
                "supplier_id": s["supplier_id"],
                "supplier_name": s["supplier_name"],
                "sensitive_fields": sensitive,
            })

    result = {
        "detected_records": detected,
        "total_detected": len(detected),
        "supplier_ids_affected": [d["supplier_id"] for d in detected],
    }
    (artifacts / "detect_sensitive_fields_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "detect_sensitive_fields_status.json").write_text(
        json.dumps({"success": True, "sensitive_records_found": len(detected), "errors": []}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
