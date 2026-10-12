#!/usr/bin/env python3
"""Mock fraud risk analyzer for daily transaction CSV batches."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

# Merchant categories with elevated risk weights
HIGH_RISK_CATEGORIES = {"crypto_exchange", "money_transfer", "gambling", "prepaid_card"}
HIGH_AMOUNT_THRESHOLD = 5000.0


def compute_row_score(amount: float, category: str) -> float:
    score = 0.0
    if amount > HIGH_AMOUNT_THRESHOLD:
        score += min(0.6, amount / 20000.0)
    if category.lower() in HIGH_RISK_CATEGORIES:
        score += 0.4
    return min(round(score, 4), 1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--execution-time", type=str, default=None)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    dataset_path = artifacts / "transactions.csv"
    shutil.copyfile(args.fixture, dataset_path)

    with dataset_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    scored_transactions: list[dict] = []
    for row in rows:
        amount = float(row["amount"])
        category = row["merchant_category"]
        score = compute_row_score(amount, category)
        scored_transactions.append(
            {
                "transaction_id": row["transaction_id"],
                "score": score,
                "features": {
                    "amount": amount,
                    "merchant_category": category,
                    "customer_id": row["customer_id"],
                },
            }
        )

    max_score = max((txn["score"] for txn in scored_transactions), default=0.0)

    risk_score = {
        "score": round(max_score, 4),
        "score_range": "0_to_1",
        "transactions_scored": len(scored_transactions),
        "aggregate_score_method": "max",
        "risk_model_profile": "deterministic_rule_based_v1",
    }
    (artifacts / "risk_score.json").write_text(
        json.dumps(risk_score, indent=2) + "\n", encoding="utf-8"
    )

    scored_doc = {"transactions": scored_transactions}
    (artifacts / "scored_transactions.json").write_text(
        json.dumps(scored_doc, indent=2) + "\n", encoding="utf-8"
    )

    scoring_status = {
        "success": True,
        "rows_read": len(rows),
        "rows_scored": len(scored_transactions),
        "risk_model_profile": "deterministic_rule_based_v1",
        "execution_time": args.execution_time,
        "errors": [],
    }
    (artifacts / "scoring_status.json").write_text(
        json.dumps(scoring_status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
