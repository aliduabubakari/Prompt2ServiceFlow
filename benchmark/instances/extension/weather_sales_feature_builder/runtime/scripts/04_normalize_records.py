#!/usr/bin/env python3
"""Normalize records: derive weather-impact features, revenue-per-sqm, and anomaly flags."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace
    artifacts = root / "artifacts"

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    config = fixture.get("feature_config", {})
    temp_high = config.get("temp_high_threshold", 28.0)
    temp_low = config.get("temp_low_threshold", 10.0)
    rain_heavy = config.get("rain_heavy_threshold_mm", 8.0)
    rev_benchmark = config.get("revenue_per_sqm_benchmark", 12.0)

    staged_data = json.loads((artifacts / "stage_raw_artifacts_artifact.json").read_text(encoding="utf-8"))

    normalized = []
    for r in staged_data["staged_records"]:
        temp = r.get("temp_c") or 0
        precip = r.get("precipitation_mm") or 0
        size = r.get("store_size_sqm") or 1

        # Weather impact features
        temp_impact = "high" if temp >= temp_high else ("low" if temp <= temp_low else "normal")
        rain_impact = "heavy" if precip >= rain_heavy else ("light" if precip > 0 else "none")

        # Revenue per sqm
        rev_per_sqm = round(r["revenue"] / size, 2)

        # Anomaly flag: high temp + ice_cream sales surge, or rain + low revenue
        anomaly = False
        if temp_impact == "high" and r.get("top_category") == "ice_cream" and rev_per_sqm > rev_benchmark * 1.5:
            anomaly = True
        if rain_impact == "heavy" and rev_per_sqm < rev_benchmark * 0.5:
            anomaly = True

        normalized.append({
            "store_id": r["store_id"],
            "city": r["city"],
            "date": r["date"],
            "revenue": r["revenue"],
            "transactions": r["transactions"],
            "top_category": r.get("top_category", ""),
            "temp_c": temp,
            "weather_condition": r.get("weather_condition", ""),
            "temp_impact": temp_impact,
            "precipitation_mm": precip,
            "rain_impact": rain_impact,
            "store_size_sqm": size,
            "store_type": r.get("store_type", ""),
            "revenue_per_sqm": rev_per_sqm,
            "weather_anomaly": anomaly,
        })

    result = {
        "normalized_features": normalized,
        "feature_count": len(normalized),
        "anomalies_detected": sum(1 for n in normalized if n["weather_anomaly"]),
        "config_used": config,
    }
    (artifacts / "normalize_records_artifact.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (artifacts / "normalize_records_status.json").write_text(
        json.dumps({"success": True, "records_normalized": len(normalized),
                     "anomalies": sum(1 for n in normalized if n["weather_anomaly"]), "errors": []}, indent=2) + "\n",
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
