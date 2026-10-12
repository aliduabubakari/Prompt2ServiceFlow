#!/usr/bin/env python3
"""Publish safe content to the platform."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    scored = json.loads((artifacts / "scored_content_dataset.json").read_text(encoding="utf-8"))
    routing = json.loads((artifacts / "toxicity_routing_decision.json").read_text(encoding="utf-8"))

    if not routing["safety_passed"]:
        raise SystemExit("Content not safe; publish action not applicable")

    refs = [it["content_id"] for it in scored["items"]]

    results = {
        "items_published": len(refs),
        "success": True,
        "publication_mode": "standard",
        "bounded_content_refs": refs,
        "errors": [],
    }
    (artifacts / "publication_results.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "publication_attempted": True,
        "errors": [],
    }
    (artifacts / "publication_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
