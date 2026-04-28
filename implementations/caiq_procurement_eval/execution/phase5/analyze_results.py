"""Phase 5 — Compliance Analysis and Reporting.

PURPOSE:
    Reads metrics.jsonl produced by Phase 4 and produces:

        output/summary.csv          — compliance rates by vendor × CCM domain
        output/summary.xlsx         — Excel workbook with 4 sheets:
                                        by_vendor         (overall pass rate per vendor)
                                        by_vendor_domain  (pass rate per vendor × domain)
                                        gap_counts        (non_compliant count per vendor)
                                        evidence_quality  (evidence rating distribution)
        output/analysis_report.md   — full markdown report with tables, observations,
                                        and per-vendor gap summaries

PASTE TO:
    <repo-root>/implementations/caiq_procurement_eval/execution/phase5/analyze_results.py

RUN WITH (from repo root):
    uv run --env-file .env --group caiq-procurement-eval \
        python implementations/caiq_procurement_eval/execution/phase5/analyze_results.py \
        --metrics implementations/caiq_procurement_eval/execution/phase4/output/metrics.jsonl \
        --out implementations/caiq_procurement_eval/execution/phase5/output/summary

WHAT TO CHECK AFTER RUNNING:
    1. Terminal shows compliance rate table by vendor
    2. output/ folder contains summary.csv, summary.xlsx, analysis_report.md
    3. Review analysis_report.md for gap patterns and LLM judge score distribution
    4. Share summary.xlsx with stakeholders as the compliance report artifact
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ALL_JUDGE_METRICS = [
    "judge_evidence_quality",
    "judge_verdict_accuracy",
    "judge_gap_clarity",
    "judge_evidence_traceability",
    "judge_reasoning_soundness",
]

VERDICT_SCORE_MAP = {
    "compliant": 1.0,
    "partial": 0.5,
    "non_compliant": 0.0,
    "needs_clarification": 0.0,
    "not_applicable": None,
}


# ──────────────────────────────────────────────────────────────
# LOAD METRICS
# ──────────────────────────────────────────────────────────────

def load_metrics(metrics_file: str) -> list[dict]:
    """Load metrics.jsonl produced by Phase 4."""
    path = Path(metrics_file)
    if not path.exists():
        logger.error("Metrics file not found: %s", path)
        sys.exit(1)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    logger.info("Loaded %d metric rows from %s", len(rows), path.name)
    return rows


# ──────────────────────────────────────────────────────────────
# DATAFRAME BUILDING
# ──────────────────────────────────────────────────────────────

def build_dataframe(rows: list[dict]) -> "pd.DataFrame":  # type: ignore[name-defined]
    """Build a pandas DataFrame from metrics rows."""
    import pandas as pd

    df = pd.DataFrame(rows)

    # Ensure compliance_score is numeric
    df["compliance_score"] = pd.to_numeric(df.get("compliance_score"), errors="coerce")

    # Normalise judge columns
    for m in ALL_JUDGE_METRICS:
        if m in df.columns:
            df[m] = pd.to_numeric(df[m], errors="coerce")

    return df


# ──────────────────────────────────────────────────────────────
# AGGREGATION
# ──────────────────────────────────────────────────────────────

def compute_vendor_summary(df: "pd.DataFrame") -> "pd.DataFrame":  # type: ignore[name-defined]
    """Overall compliance rate by vendor."""
    scored = df[df["compliance_score"].notna()].copy()
    summary = (
        scored.groupby("vendor")["compliance_score"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "compliance_rate", "count": "n_questions"})
        .reset_index()
    )
    summary["compliance_rate"] = summary["compliance_rate"].round(3)

    # Add judge metric averages per vendor if present
    for m in ALL_JUDGE_METRICS:
        if m in df.columns:
            judge_avg = df.groupby("vendor")[m].mean().round(3).reset_index(name=m)
            summary = summary.merge(judge_avg, on="vendor", how="left")

    return summary


def compute_domain_summary(df: "pd.DataFrame") -> "pd.DataFrame":  # type: ignore[name-defined]
    """Compliance rate by vendor × CCM domain."""
    scored = df[df["compliance_score"].notna()].copy()
    return (
        scored.groupby(["vendor", "domain_id"])["compliance_score"]
        .agg(["mean", "count"])
        .rename(columns={"mean": "compliance_rate", "count": "n_questions"})
        .reset_index()
        .round({"compliance_rate": 3})
    )


def compute_gap_counts(df: "pd.DataFrame") -> "pd.DataFrame":  # type: ignore[name-defined]
    """Count of non_compliant verdicts per vendor."""
    return (
        df[df["final_verdict"] == "non_compliant"]
        .groupby("vendor")
        .size()
        .reset_index(name="gap_count")
    )


def compute_evidence_distribution(df: "pd.DataFrame") -> "pd.DataFrame":  # type: ignore[name-defined]
    """Evidence quality counts per vendor (pivoted)."""
    return (
        df.groupby(["vendor", "evidence_quality"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )


# ──────────────────────────────────────────────────────────────
# MARKDOWN REPORT
# ──────────────────────────────────────────────────────────────

def generate_report(
    df: "pd.DataFrame",  # type: ignore[name-defined]
    vendor_summary: "pd.DataFrame",  # type: ignore[name-defined]
    domain_summary: "pd.DataFrame",  # type: ignore[name-defined]
    gap_counts: "pd.DataFrame",  # type: ignore[name-defined]
) -> str:
    """Generate a full markdown compliance analysis report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    n_total = len(df)
    n_vendors = df["vendor"].nunique()
    n_domains = df["domain_id"].nunique()

    lines = [
        "# CAIQ Vendor Compliance Analysis Report",
        "",
        f"**Generated:** {now}  ",
        f"**Total Samples:** {n_total}  ",
        f"**Vendors:** {n_vendors}  ",
        f"**CCM Domains:** {n_domains}",
        "",
        "---",
        "",
        "## 1. Compliance Rate by Vendor",
        "",
    ]

    # Vendor summary table
    lines.append("| Vendor | Compliance Rate | N Questions | Verdict Distribution |")
    lines.append("|---|---|---|---|")
    for _, row in vendor_summary.iterrows():
        rate = row.get("compliance_rate", 0)
        bar = _bar(rate)
        verdict_dist = _verdict_dist(df[df["vendor"] == row["vendor"]])
        lines.append(
            f"| {row['vendor']} | {bar} {rate:.0%} | {int(row['n_questions'])} | {verdict_dist} |"
        )

    lines += ["", "---", "", "## 2. Compliance Rate by Vendor × CCM Domain", ""]

    # Domain × vendor table (pivoted)
    if len(domain_summary) > 0:
        vendors = sorted(df["vendor"].unique())
        domains = sorted(domain_summary["domain_id"].unique())

        header = "| Domain |" + "".join(f" {v[:12]} |" for v in vendors)
        sep = "|---|" + "---|" * len(vendors)
        lines.append(header)
        lines.append(sep)

        for domain in domains:
            row_vals = [f" {domain} |"]
            for vendor in vendors:
                sub = domain_summary[
                    (domain_summary["domain_id"] == domain) & (domain_summary["vendor"] == vendor)
                ]
                if len(sub) == 0:
                    row_vals.append(" — |")
                else:
                    rate = sub.iloc[0]["compliance_rate"]
                    n = int(sub.iloc[0]["n_questions"])
                    row_vals.append(f" {rate:.0%} ({n}) |")
            lines.append("|" + "".join(row_vals))

    lines += ["", "---", "", "## 3. Compliance Gaps", ""]

    if len(gap_counts) == 0:
        lines.append("No non-compliant verdicts found.")
    else:
        lines.append("| Vendor | Non-Compliant Count |")
        lines.append("|---|---|")
        for _, row in gap_counts.sort_values("gap_count", ascending=False).iterrows():
            lines.append(f"| {row['vendor']} | {int(row['gap_count'])} |")

        # Per-vendor gap details
        lines += ["", "### Gap Details by Vendor", ""]
        for vendor in sorted(gap_counts["vendor"].unique()):
            gaps = df[(df["vendor"] == vendor) & (df["final_verdict"] == "non_compliant")]
            if len(gaps) == 0:
                continue
            lines.append(f"**{vendor}** — {len(gaps)} gap(s):\n")
            for _, g in gaps.iterrows():
                desc = g.get("gap_description", "").strip() or "No description available"
                lines.append(f"- `{g.get('question_id', '')}` [{g.get('domain_id', '')}]: {desc[:200]}")
            lines.append("")

    lines += ["", "---", "", "## 4. Evidence Quality Distribution", ""]

    eq_counts = df.groupby(["vendor", "evidence_quality"]).size().unstack(fill_value=0)
    eq_cols = [c for c in ["strong", "moderate", "weak", "absent"] if c in eq_counts.columns]
    if eq_cols:
        header = "| Vendor |" + "".join(f" {c.capitalize()} |" for c in eq_cols)
        sep = "|---|" + "---|" * len(eq_cols)
        lines.append(header)
        lines.append(sep)
        for vendor, row in eq_counts.iterrows():
            vals = "".join(f" {int(row.get(c, 0))} |" for c in eq_cols)
            lines.append(f"| {vendor} |{vals}")

    # Judge scores section if present
    judge_cols = [m for m in ALL_JUDGE_METRICS if m in df.columns]
    if judge_cols:
        lines += ["", "---", "", "## 5. LLM Judge Score Summary", ""]
        lines.append("| Metric | Mean Score | Vendors |")
        lines.append("|---|---|---|")
        for m in judge_cols:
            vals = df[m].dropna()
            mean_val = vals.mean() if len(vals) > 0 else None
            bar = _bar(mean_val)
            score_str = f"{bar} {mean_val:.2f}" if mean_val is not None else "—"
            lines.append(f"| `{m.replace('judge_', '')}` | {score_str} | {len(vals)} |")

    lines += [
        "",
        "---",
        "",
        "*Generated by CAIQ Procurement Eval — Phase 5 analysis script.*",
    ]

    return "\n".join(lines)


def _bar(rate: float | None, width: int = 8) -> str:
    """Simple ASCII progress bar."""
    if rate is None:
        return "[" + "?" * width + "]"
    filled = round(rate * width)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def _verdict_dist(sub_df: "pd.DataFrame") -> str:  # type: ignore[name-defined]
    """Short verdict distribution string."""
    counts = sub_df["final_verdict"].value_counts()
    parts = []
    for verdict, label in [("compliant", "C"), ("partial", "P"), ("non_compliant", "NC"), ("not_applicable", "NA")]:
        n = counts.get(verdict, 0)
        if n > 0:
            parts.append(f"{label}:{n}")
    return " ".join(parts) if parts else "—"


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────

def main() -> None:
    """Parse args and generate compliance summary + report."""
    parser = argparse.ArgumentParser(description="Phase 5 — Compliance analysis and reporting")
    parser.add_argument("--metrics", required=True, help="Path to metrics.jsonl from Phase 4")
    parser.add_argument(
        "--out",
        default="implementations/caiq_procurement_eval/execution/phase5/output/summary",
        help="Output path stem (extensions .csv, .xlsx, _report.md added automatically)",
    )
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    try:
        import pandas as pd  # noqa: F401
    except ImportError:
        logger.error("pandas is required: uv add pandas")
        sys.exit(1)

    out_stem = Path(args.out)
    out_stem.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Phase 5: Compliance Analysis ===\n")
    print(f"  Metrics file : {args.metrics}")
    print(f"  Output stem  : {args.out}")
    print()

    # ── 1. Load ──
    rows = load_metrics(args.metrics)
    if not rows:
        logger.error("No metrics found in %s", args.metrics)
        sys.exit(1)

    df = build_dataframe(rows)

    # ── 2. Aggregate ──
    vendor_summary = compute_vendor_summary(df)
    domain_summary = compute_domain_summary(df)
    gap_counts = compute_gap_counts(df)
    evidence_dist = compute_evidence_distribution(df)

    # ── 3. Write CSV ──
    csv_path = out_stem.with_suffix(".csv")
    domain_summary.to_csv(csv_path, index=False)
    logger.info("Saved: %s", csv_path)

    # ── 4. Write Excel workbook ──
    xlsx_path = out_stem.with_suffix(".xlsx")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:  # type: ignore[attr-defined]
        vendor_summary.to_excel(writer, sheet_name="by_vendor", index=False)
        domain_summary.to_excel(writer, sheet_name="by_vendor_domain", index=False)
        gap_counts.to_excel(writer, sheet_name="gap_counts", index=False)
        evidence_dist.to_excel(writer, sheet_name="evidence_quality", index=False)
    logger.info("Saved: %s", xlsx_path)

    # ── 5. Write markdown report ──
    report_path = out_stem.parent / (out_stem.name + "_report.md")
    report_md = generate_report(df, vendor_summary, domain_summary, gap_counts)
    report_path.write_text(report_md, encoding="utf-8")
    logger.info("Saved: %s", report_path)

    # ── 6. Console summary ──
    print("\n" + "=" * 65)
    print("  COMPLIANCE RATE BY VENDOR")
    print("=" * 65)
    for _, row in vendor_summary.iterrows():
        rate = row.get("compliance_rate", 0)
        bar = _bar(rate)
        n = int(row.get("n_questions", 0))
        print(f"  {row['vendor']:<30} {bar} {rate:.0%}  ({n} questions)")

    print(f"\n  Total non-compliant gaps  : {len(df[df['final_verdict'] == 'non_compliant'])}")
    print(f"  Total partial compliance  : {len(df[df['final_verdict'] == 'partial'])}")
    print(f"  Total compliant           : {len(df[df['final_verdict'] == 'compliant'])}")
    print(f"  Total not applicable      : {len(df[df['final_verdict'] == 'not_applicable'])}")

    print(f"\n  Output files:")
    print(f"    {csv_path}")
    print(f"    {xlsx_path}")
    print(f"    {report_path}")

    print("\n  -> Review analysis_report.md for full compliance breakdown.")
    print("  -> Share summary.xlsx as the vendor compliance report artifact.")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
