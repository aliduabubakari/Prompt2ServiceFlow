#!/usr/bin/env python3
"""Validate source contracts: required fields, farmer references, crop type validity."""
from __future__ import annotations
import argparse, json
from pathlib import Path

REQUIRED_IMAGE_FIELDS = {"image_id", "farmer_id", "crop_type", "image_quality_score", "symptoms_observed"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace; artifacts = root / "artifacts"

    ingested = json.loads((artifacts / "ingest_source_batch_artifact.json").read_text(encoding="utf-8"))
    images, farmers, policy = ingested["images"], ingested["farmers"], ingested["policy"]
    crop_profiles = policy["crop_risk_profiles"]

    errors = []; valid_images = []
    for img in images:
        issues = []
        missing = REQUIRED_IMAGE_FIELDS - set(img.keys())
        if missing: issues.append(f"missing_fields: {missing}")
        if img.get("farmer_id") not in farmers: issues.append(f"unknown_farmer: {img.get('farmer_id')}")
        if img.get("crop_type") not in crop_profiles: issues.append(f"unknown_crop: {img.get('crop_type')}")
        qs = img.get("image_quality_score", 0)
        if not (0 <= qs <= 1): issues.append(f"invalid_quality_score: {qs}")
        if issues:
            errors.append({"image_id": img.get("image_id","?"), "issues": issues})
        else:
            valid_images.append(img)

    result = {"valid_images": valid_images, "total_errors": len(errors), "errors": errors}
    (artifacts / "validate_source_contract_artifact.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (artifacts / "validate_source_contract_status.json").write_text(
        json.dumps({"success": True, "valid": len(valid_images), "rejected": len(errors), "errors": errors}, indent=2) + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
