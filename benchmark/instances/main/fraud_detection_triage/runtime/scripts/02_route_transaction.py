#!/usr/bin/env python3
"""Apply risk threshold and emit deterministic routing decision."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


THRESHOLD = 0.8
MANUAL_REVIEW_LABEL = "manual_review"
AUTO_APPROVE_LABEL = "auto_approve"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    risk_score = json.loads((artifacts / "risk_score.json").read_text(encoding="utf-8"))
    score = risk_score["score"]
    manual_review = score > THRESHOLD
    auto_approve = score <= THRESHOLD
    route = MANUAL_REVIEW_LABEL if manual_review else AUTO_APPROVE_LABEL

    decision = {
        "score": score,
        "risk_threshold": THRESHOLD,
        "route": route,
        "manual_review": manual_review,
        "auto_approve": auto_approve,
        "reason": f"Score {score} {'>' if manual_review else '<='} threshold {THRESHOLD}",
    }
    (artifacts / "routing_decision.json").write_text(
        json.dumps(decision, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "route.txt").write_text(route, encoding="utf-8")


if __name__ == "__main__":
    main()
