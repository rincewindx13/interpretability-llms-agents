# Phase 5 — Compliance Analysis & Reporting

Reads `metrics.jsonl` from Phase 4 and generates a full compliance report.

## Run

```bash
uv run --env-file .env --group caiq-procurement-eval \
    python implementations/caiq_procurement_eval/execution/phase5/analyze_results.py \
    --metrics implementations/caiq_procurement_eval/execution/phase4/output/metrics.jsonl \
    --out implementations/caiq_procurement_eval/execution/phase5/output/summary
```

## Output files

| File | Contents |
|---|---|
| `summary.csv` | Compliance rate by vendor × CCM domain |
| `summary.xlsx` | Excel workbook (4 sheets) |
| `summary_report.md` | Full markdown report with tables and gap details |

## Excel workbook sheets

| Sheet | Contents |
|---|---|
| `by_vendor` | Overall compliance rate + judge score averages per vendor |
| `by_vendor_domain` | Compliance rate per vendor × CCM domain |
| `gap_counts` | Count of non-compliant verdicts per vendor |
| `evidence_quality` | Evidence quality distribution (strong / moderate / weak / absent) |

## Sample console output

```
=================================================================
  COMPLIANCE RATE BY VENDOR
=================================================================
  Vendor A                       [████████░░] 80%  (45 questions)
  Vendor B                       [█████░░░░░] 52%  (48 questions)

  Total non-compliant gaps  : 18
  Total partial compliance  : 12
  Total compliant           : 73
  Total not applicable      : 7
=================================================================
```
