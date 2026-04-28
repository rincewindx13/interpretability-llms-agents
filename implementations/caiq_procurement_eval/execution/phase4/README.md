# Phase 4 — CEP Evaluation (Verdicts + LLM Judge)

Reads CEP JSON files from Phase 3 and produces a `metrics.jsonl` file with
compliance scores and LLM-as-judge rubric scores.

## Run

```bash
# With LLM judge (default — recommended):
uv run --env-file .env --group caiq-procurement-eval \
    python implementations/caiq_procurement_eval/execution/phase4/run_eval.py \
    --cep_dir implementations/caiq_procurement_eval/execution/phase3/ceps/gemini_gemini/ \
    --out implementations/caiq_procurement_eval/execution/phase4/output/metrics.jsonl

# Without judge (faster, for quick iteration):
uv run --env-file .env --group caiq-procurement-eval \
    python implementations/caiq_procurement_eval/execution/phase4/run_eval.py \
    --cep_dir implementations/caiq_procurement_eval/execution/phase3/ceps/gemini_gemini/ \
    --out implementations/caiq_procurement_eval/execution/phase4/output/metrics.jsonl \
    --no_judge
```

## Compliance score mapping

| Verdict | Score |
|---|---|
| `compliant` | 1.0 |
| `partial` | 0.5 |
| `non_compliant` | 0.0 |
| `needs_clarification` | 0.0 |
| `not_applicable` | None (excluded from rate) |

## LLM judge rubrics (5 scores, each 0–1)

| Rubric | What it measures |
|---|---|
| `judge_evidence_quality` | Is the evidence strong and specific? |
| `judge_verdict_accuracy` | Does the verdict match the evidence? |
| `judge_gap_clarity` | Is the gap description clear and actionable? |
| `judge_evidence_traceability` | Can the evidence be traced to a real control? |
| `judge_reasoning_soundness` | Is the reasoning logically coherent? |

## Output schema (metrics.jsonl)

Each line is a JSON object with:
- `sample_id`, `vendor`, `question_id`, `domain_id`, `vendor_answer`
- `evaluator_verdict`, `verifier_verdict`, `final_verdict`
- `compliance_score`, `confidence`, `evidence_quality`
- `gap_description`, `evidence_citation`, `latency_sec`
- `judge_*` (if judge enabled)
