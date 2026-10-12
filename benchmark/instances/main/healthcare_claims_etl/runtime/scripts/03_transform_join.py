#!/usr/bin/env python3
"""Join claims and providers, pseudonymize patient IDs, compute risk scores."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def pseudonymize(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def compute_risk(amount: float, procedure: str) -> float:
    procedure_risk = {"PROC_A": 0.3, "PROC_B": 0.7, "PROC_C": 0.5}
    pr = procedure_risk.get(procedure, 0.5)
    amount_norm = min(float(amount) / 5000.0, 1.0)
    return round(0.5 * amount_norm + 0.5 * pr, 4)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    claims = json.loads((artifacts / "claims_dataset.json").read_text(encoding="utf-8"))
    providers = json.loads((artifacts / "providers_dataset.json").read_text(encoding="utf-8"))

    prov_map = {r["provider_id"]: r for r in providers["rows"]}
    joined_rows = []
    for claim in claims["rows"]:
        prov = prov_map.get(claim["provider_id"], {})
        joined = {
            "claim_id": claim["claim_id"],
            "patient_id": pseudonymize(claim["patient_id"]),
            "provider_id": claim["provider_id"],
            "provider_name": prov.get("provider_name", ""),
            "specialty": prov.get("specialty", ""),
            "procedure_code": claim["procedure_code"],
            "amount": float(claim["amount"]),
            "risk_score": compute_risk(float(claim["amount"]), claim["procedure_code"]),
            "date_of_service": claim["date_of_service"],
        }
        joined_rows.append(joined)

    columns = [
        "claim_id", "patient_id", "provider_id", "provider_name", "specialty",
        "procedure_code", "amount", "risk_score", "date_of_service",
    ]
    output = {"columns": columns, "rows": joined_rows}
    (artifacts / "transformed_healthcare_dataset.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "rows_joined": len(joined_rows),
        "anonymization_applied": True,
        "errors": [],
    }
    (artifacts / "transform_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
