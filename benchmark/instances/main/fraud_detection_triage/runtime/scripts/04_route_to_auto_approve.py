#!/usr/bin/env python3
"""Record auto-approval branch processing status."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


THRESHOLD = 0.8


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    routing = json.loads((artifacts / "routing_decision.json").read_text(encoding="utf-8"))
    scored = json.loads((artifacts / "scored_transactions.json").read_text(encoding="utf-8"))

    # Validate that auto-approval route was selected
    if not routing["auto_approve"]:
        raise SystemExit("Auto-approval route not selected in routing decision")

    transactions = scored["transactions"]
    bounded_refs = [
        txn["transaction_id"] for txn in transactions if txn["score"] <= THRESHOLD
    ][:100]

    status = {
        "success": True,
        "route": routing["route"],
        "auto_approval_recorded": routing["auto_approve"],
        "transactions_auto_approved": len(transactions),
        "bounded_transaction_refs": bounded_refs,
        "errors": [],
    }
    (artifacts / "auto_approval_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
