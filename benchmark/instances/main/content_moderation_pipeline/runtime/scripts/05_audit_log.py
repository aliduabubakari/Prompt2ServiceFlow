#!/usr/bin/env python3
"""Create audit log entry at the moderation merge point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"

    action_path = artifacts / "moderation_action_results.json"
    pub_path = artifacts / "publication_results.json"

    event_type = "unknown"
    bounded_refs: list[str] = []
    if action_path.is_file():
        action = json.loads(action_path.read_text(encoding="utf-8"))
        event_type = action.get("action_type", "moderation_action")
        bounded_refs = action.get("bounded_content_refs", [])
    elif pub_path.is_file():
        pub = json.loads(pub_path.read_text(encoding="utf-8"))
        event_type = "safe_publication"
        bounded_refs = pub.get("bounded_content_refs", [])

    entry = {
        "audit_event_type": event_type,
        "audit_record_created": True,
        "success": True,
        "workflow_id": "content_moderation_pipeline",
        "bounded_references": bounded_refs,
        "errors": [],
    }
    (artifacts / "audit_log_entry.json").write_text(
        json.dumps(entry, indent=2) + "\n", encoding="utf-8"
    )
    status = {
        "success": True,
        "audit_attempted": True,
        "errors": [],
    }
    (artifacts / "audit_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
