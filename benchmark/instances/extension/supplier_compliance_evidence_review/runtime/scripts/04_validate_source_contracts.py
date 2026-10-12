#!/usr/bin/env python3
"""Validate source contracts: cross-reference suppliers, check cert freshness, identify gaps."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timedelta
from pathlib import Path


def parse_date(d: str) -> datetime:
    return datetime.strptime(d, "%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace
    artifacts = root / "artifacts"

    primary = json.loads((artifacts / "ingest_primary_source_artifact.json").read_text(encoding="utf-8"))
    secondary = json.loads((artifacts / "ingest_secondary_source_artifact.json").read_text(encoding="utf-8"))
    reference = json.loads((artifacts / "ingest_reference_source_artifact.json").read_text(encoding="utf-8"))

    certificates = primary["certificates"]
    suppliers = {s["supplier_id"]: s for s in secondary["suppliers"]}
    policy = reference["policy"]
    expiry_grace = timedelta(days=policy["expiry_grace_days"])
    today = datetime(2026, 7, 20)  # fixed reference date

    issues = []
    validated_certs = []
    cert_supplier_ids = set()

    for cert in certificates:
        sid = cert["supplier_id"]
        cert_supplier_ids.add(sid)
        cert_issues = []

        # Check supplier exists in master
        if sid not in suppliers:
            cert_issues.append(f"orphan_cert: supplier {sid} not in master")

        # Check expiry
        if cert["status"] == "expired":
            cert_issues.append("cert_expired")
        else:
            expiry = parse_date(cert["expiry_date"])
            if today + expiry_grace >= expiry:
                cert_issues.append("cert_near_expiry")

        # Check cert type is required
        if cert["cert_type"] not in policy["required_cert_types"]:
            cert_issues.append(f"non_required_cert_type: {cert['cert_type']}")

        if cert_issues:
            issues.append({
                "cert_id": cert["cert_id"],
                "supplier_id": sid,
                "issues": cert_issues,
            })

        validated_certs.append({**cert, "validation_issues": cert_issues})

    # Check suppliers without any certs
    master_supplier_ids = set(suppliers.keys())
    missing_cert_suppliers = master_supplier_ids - cert_supplier_ids
    for sid in missing_cert_suppliers:
        issues.append({
            "supplier_id": sid,
            "issues": ["missing_certificates"],
        })

    result = {
        "validated_certs": validated_certs,
        "suppliers": {sid: {**s, "has_certs": sid in cert_supplier_ids} for sid, s in suppliers.items()},
        "missing_cert_suppliers": sorted(missing_cert_suppliers),
        "orphan_cert_suppliers": sorted(cert_supplier_ids - master_supplier_ids),
        "total_issues": len(issues),
        "issues": issues,
        "reference_date": today.isoformat(),
    }
    (artifacts / "validate_source_contracts_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "validate_source_contracts_status.json").write_text(
        json.dumps({"success": True, "issues_found": len(issues), "errors": issues}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
