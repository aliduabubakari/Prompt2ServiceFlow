#!/usr/bin/env python3
"""Normalize sources: combine cert and supplier data into unified per-supplier records."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace
    artifacts = root / "artifacts"

    validated = json.loads((artifacts / "validate_source_contracts_artifact.json").read_text(encoding="utf-8"))
    validated_certs = validated["validated_certs"]
    suppliers = validated["suppliers"]

    # Normalize: build per-supplier unified records
    normalized = []
    for sid, supplier in suppliers.items():
        supplier_certs = [c for c in validated_certs if c["supplier_id"] == sid]
        active_certs = [c for c in supplier_certs if c["status"] == "active"]
        expired_certs = [c for c in supplier_certs if c["status"] == "expired"]

        record = {
            "supplier_id": sid,
            "supplier_name": supplier["supplier_name"],
            "tax_id": supplier.get("tax_id", ""),
            "bank_account": supplier.get("bank_account", ""),
            "contact_email": supplier.get("contact_email", ""),
            "country": supplier.get("country", ""),
            "risk_tier": supplier.get("risk_tier", "unknown"),
            "total_certs": len(supplier_certs),
            "active_certs": len(active_certs),
            "expired_certs": len(expired_certs),
            "cert_types": [c["cert_type"] for c in supplier_certs],
            "has_min_active": len(active_certs) >= 1,
            "cert_issues": [c.get("validation_issues", []) for c in supplier_certs],
        }
        normalized.append(record)

    result = {
        "normalized_suppliers": normalized,
        "total_suppliers": len(normalized),
        "suppliers_with_certs": sum(1 for s in normalized if s["total_certs"] > 0),
        "suppliers_without_certs": sum(1 for s in normalized if s["total_certs"] == 0),
    }
    (artifacts / "normalize_sources_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "normalize_sources_status.json").write_text(
        json.dumps({"success": True, "normalized": len(normalized), "errors": []}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
