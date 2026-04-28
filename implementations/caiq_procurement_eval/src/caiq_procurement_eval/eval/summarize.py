"""Aggregate metrics.jsonl into a summary CSV by vendor × domain."""

import argparse
import json
from pathlib import Path

import pandas as pd


def summarize(metrics_file: str, out_file: str) -> None:
    """Aggregate per-item metrics into pass rates by vendor and CCM domain.

    Parameters
    ----------
    metrics_file : str
        Path to JSONL file produced by eval_outputs.
    out_file : str
        Output CSV path.
    """
    rows = [json.loads(line) for line in Path(metrics_file).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        print("No metrics found.")
        return

    df = pd.DataFrame(rows)

    # Compliance rate: compliant=1.0, partial=0.5, non_compliant=0.0 (NA excluded)
    scored = df[df["compliance_score"].notna()].copy()
    scored["compliance_score"] = scored["compliance_score"].astype(float)

    # Overall by vendor
    vendor_summary = (
        scored.groupby("vendor")["compliance_score"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "compliance_rate", "count": "n_questions"})
        .reset_index()
    )

    # By vendor × domain
    domain_summary = (
        scored.groupby(["vendor", "domain_id"])["compliance_score"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "compliance_rate", "count": "n_questions"})
        .reset_index()
    )

    # Gap count (non_compliant) per vendor
    gap_counts = (
        df[df["final_verdict"] == "non_compliant"]
        .groupby("vendor")
        .size()
        .reset_index(name="gap_count")
    )

    # Evidence quality distribution per vendor
    evidence_dist = (
        df.groupby(["vendor", "evidence_quality"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    # Write summary CSV
    out_path = Path(out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(out_path.with_suffix(".xlsx"), engine="openpyxl") as writer:
        vendor_summary.to_excel(writer, sheet_name="by_vendor", index=False)
        domain_summary.to_excel(writer, sheet_name="by_vendor_domain", index=False)
        gap_counts.to_excel(writer, sheet_name="gap_counts", index=False)
        evidence_dist.to_excel(writer, sheet_name="evidence_quality", index=False)

    domain_summary.to_csv(out_path, index=False)

    print(f"\nSummary written to: {out_path}")
    print(f"Excel workbook   : {out_path.with_suffix('.xlsx')}")
    print("\n--- Compliance Rate by Vendor ---")
    print(vendor_summary.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise CEP metrics into compliance report")
    parser.add_argument("--metrics", required=True, help="Path to metrics.jsonl")
    parser.add_argument("--out", default="output/summary.csv", help="Output CSV path")
    args = parser.parse_args()
    summarize(args.metrics, args.out)


if __name__ == "__main__":
    main()
