#!/usr/bin/env python3
"""Apply remove-and-flag moderation action to toxic content."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

THRESHOLD = 0.7


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    scored = json.loads((artifacts / "scored_content_dataset.json").read_text(encoding="utf-8"))
    routing = json.loads((artifacts / "toxicity_routing_decision.json").read_text(encoding="utf-8"))

    if not routing["toxicity_exceeded"]:
        raise SystemExit("Toxicity not exceeded; remove-flag action not applicable")

    toxic_items = [it for it in scored["items"] if it.get("toxicity_score", 0) > THRESHOLD]
    refs = [it["content_id"] for it in toxic_items]

    results = {
        "action_type": "remove_and_flag",
        "items_affected": len(toxic_items),
        "success": True,
        "bounded_content_refs": refs,
        "errors": [],
    }
    (artifacts / "moderation_action_results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "action_applied": True,
        "action_type": "remove_and_flag",
        "errors": [],
    }
    (artifacts / "action_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
