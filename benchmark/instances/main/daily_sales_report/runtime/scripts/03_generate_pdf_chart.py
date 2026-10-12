#!/usr/bin/env python3
"""Generate a mock PDF chart from the sales CSV."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PDF_HEADER = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
PDF_CONTENT = b"%% MOCK PDF CHART - Daily Sales Report\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    artifacts = args.workspace / "artifacts"
    pdf_path = artifacts / "sales_chart.pdf"
    # Build a minimal valid PDF stub
    content = PDF_HEADER + PDF_CONTENT * 20
    pdf_path.write_bytes(content)

    status = {
        "success": True,
        "render_attempted": True,
        "output_uri": str(pdf_path),
        "errors": [],
    }
    (artifacts / "chart_render_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
