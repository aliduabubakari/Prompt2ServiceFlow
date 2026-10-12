#!/usr/bin/env python3
"""Export, convert, and aggregate deterministic regional sales fixtures."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


REGIONS = ("us_east", "us_west", "eu", "apac")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--step", choices=("export", "convert", "aggregate"), required=True)
    parser.add_argument("--region", choices=REGIONS)
    parser.add_argument("--database-resource", type=Path)
    parser.add_argument("--source-fixture", type=Path)
    parser.add_argument("--exchange-rates", type=Path)
    args = parser.parse_args()
    artifacts = args.workspace / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    if args.step == "export":
        if not args.region or not args.database_resource or not args.source_fixture:
            raise SystemExit("export requires region, database resource, and source fixture")
        resource = json.loads(args.database_resource.read_text(encoding="utf-8"))
        output = artifacts / f"{args.region}_sales.csv"
        shutil.copyfile(args.source_fixture, output)
        rows = read_rows(output)
        status = {"success": True, "region": resource["region"], "rows_exported": len(rows), "errors": []}
        (artifacts / f"{args.region}_ingest_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        return
    if args.step == "convert":
        if not args.region or not args.exchange_rates:
            raise SystemExit("convert requires region and exchange rates")
        rate_document = json.loads(args.exchange_rates.read_text(encoding="utf-8"))
        rates = {row["currency"]: Decimal(str(row["rate_to_usd"])) for row in rate_document["rows"]}
        rows = read_rows(artifacts / f"{args.region}_sales.csv")
        output_rows = []
        for row in rows:
            rate = rates[row["currency"]]
            revenue = (Decimal(row["revenue"]) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            output_rows.append({"product_id": row["product_id"], "revenue_usd": f"{revenue:.2f}", "region": args.region})
        output = artifacts / f"{args.region}_usd.csv"
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["product_id", "revenue_usd", "region"])
            writer.writeheader()
            writer.writerows(output_rows)
        status = {"success": True, "region": args.region, "rows_converted": len(output_rows), "errors": []}
        (artifacts / f"{args.region}_convert_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        return
    all_rows = []
    for region in REGIONS:
        all_rows.extend(read_rows(artifacts / f"{region}_usd.csv"))
    totals: dict[str, Decimal] = {}
    for row in all_rows:
        totals[row["region"]] = totals.get(row["region"], Decimal("0")) + Decimal(row["revenue_usd"])
    output = artifacts / "global_report.csv"
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["region", "total_revenue_usd"])
        writer.writeheader()
        for region in REGIONS:
            writer.writerow({"region": region, "total_revenue_usd": f"{totals[region]:.2f}"})
    status = {
        "success": True,
        "input_file_count": len(REGIONS),
        "rows_aggregated": len(all_rows),
        "total_revenue_usd": float(sum(totals.values())),
        "errors": [],
    }
    (artifacts / "aggregate_status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
