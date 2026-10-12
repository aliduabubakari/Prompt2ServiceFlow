#!/usr/bin/env python3
"""Score content toxicity with deterministic keyword rules and emit routing decision."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

TOXIC_KEYWORDS = {"hate", "banned", "kill", "stupid", "terrible", "awful"}
THRESHOLD = 0.7
REMOVE_FLAG = "remove_flag"
PUBLISH = "publish"


def compute_toxicity(text: str) -> float:
    words = text.lower().split()
    if not words:
        return 0.0
    toxic_count = sum(1 for w in words if w in TOXIC_KEYWORDS)
    return round(min(toxic_count / len(words) * 3.0, 1.0), 4)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    scan = json.loads((artifacts / "scanned_content_dataset.json").read_text(encoding="utf-8"))

    scored_items = []
    max_score = 0.0
    for item in scan["items"]:
        score = compute_toxicity(item["content_text"])
        max_score = max(max_score, score)
        scored = dict(item)
        scored["toxicity_score"] = score
        scored_items.append(scored)

    toxic = max_score > THRESHOLD
    scored_ds = {
        "items": scored_items,
        "total_items": len(scored_items),
        "toxicity_threshold": THRESHOLD,
    }
    (artifacts / "scored_content_dataset.json").write_text(
        json.dumps(scored_ds, indent=2) + "\n", encoding="utf-8"
    )

    decision = {
        "route": REMOVE_FLAG if toxic else PUBLISH,
        "toxicity_exceeded": toxic,
        "safety_passed": not toxic,
        "threshold": THRESHOLD,
        "reason": f"max toxicity {max_score} {'>' if toxic else '<='} {THRESHOLD}",
    }
    (artifacts / "toxicity_routing_decision.json").write_text(
        json.dumps(decision, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "toxicity_route.txt").write_text(decision["route"], encoding="utf-8")


if __name__ == "__main__":
    main()
