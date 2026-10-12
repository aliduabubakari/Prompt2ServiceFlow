#!/usr/bin/env python3
"""Apply redaction: partially redact tax_ids, fully suppress bank_accounts."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def redact_partial(value: str, keep: int) -> str:
    if len(value) <= keep:
        return value
    return value[:keep] + "*" * (len(value) - keep)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace
    artifacts = root / "artifacts"

    fused_data = json.loads((artifacts / "fuse_sources_artifact.json").read_text(encoding="utf-8"))
    sensitive_data = json.loads((artifacts / "detect_sensitive_fields_artifact.json").read_text(encoding="utf-8"))
    reference = json.loads((artifacts / "ingest_reference_source_artifact.json").read_text(encoding="utf-8"))
    patterns = reference["policy"]["sensitive_field_patterns"]

    # Build set of supplier_ids with sensitive data
    affected = {d["supplier_id"]: d["sensitive_fields"] for d in sensitive_data["detected_records"]}

    redacted = []
    for s in fused_data["fused_suppliers"]:
        record = {**s}
        if s["supplier_id"] in affected:
            for field, config in affected[s["supplier_id"]].items():
                if config["redaction"] == "full":
                    record[field] = "[REDACTED]"
                elif config["redaction"] == "partial":
                    record[field] = redact_partial(s[field], config["keep_chars"])
        redacted.append(record)

    result = {
        "redacted_suppliers": redacted,
        "total_redacted": len(affected),
        "redacted_fields": list(patterns.keys()),
    }
    (artifacts / "apply_redaction_or_suppression_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "apply_redaction_or_suppression_status.json").write_text(
        json.dumps({"success": True, "records_redacted": len(affected), "errors": []}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
