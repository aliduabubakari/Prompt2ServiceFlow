#!/usr/bin/env python3
"""Evaluate risk per image: compute disease risk score and determine routing decision."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace; artifacts = root / "artifacts"

    validated = json.loads((artifacts / "validate_source_contract_artifact.json").read_text(encoding="utf-8"))
    ingested = json.loads((artifacts / "ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    policy = ingested["policy"]
    farmers = ingested["farmers"]
    quality_min = policy["image_quality_minimum"]
    profiles = policy["crop_risk_profiles"]
    thresholds = policy["risk_thresholds"]

    scored = []
    for img in validated["valid_images"]:
        qs = img["image_quality_score"]
        crop = img["crop_type"]
        symptoms = img.get("symptoms_observed", "none")
        farmer = farmers.get(img["farmer_id"], {})

        # Low quality → automatic exception
        if qs < quality_min:
            scored.append({**img, "risk_score": 0.0, "route": "exception",
                           "reason": f"low_quality: {qs} < {quality_min}"})
            continue

        # Compute disease risk
        profile = profiles.get(crop, {})
        base = profile.get("base_risk", 0.3)
        mult = profile.get("symptoms_multiplier", {}).get(symptoms, 1.0)
        risk = min(round(base * mult, 2), 1.0)

        # Disease history escalation
        if policy.get("disease_history_escalation") and farmer.get("disease_history") == "high":
            risk = min(risk + 0.15, 1.0)

        route = "exception" if risk > thresholds["high"] else "approved"
        scored.append({**img, "risk_score": risk, "route": route,
                       "reason": f"risk={risk}, thresholds=({thresholds['low']},{thresholds['high']})"})

    approved = [s for s in scored if s["route"] == "approved"]
    exceptions = [s for s in scored if s["route"] == "exception"]

    result = {"scored_images": scored, "approved": approved, "exceptions": exceptions,
              "total": len(scored), "approved_count": len(approved), "exception_count": len(exceptions)}
    (artifacts / "evaluate_policy_or_risk_artifact.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (artifacts / "evaluate_policy_or_risk_status.json").write_text(
        json.dumps({"success": True, "scored": len(scored), "approved": len(approved), "exceptions": len(exceptions), "errors": []}, indent=2) + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
