"""Phase 4 — Evaluate CEPs: Compliance Verdicts + LLM Judge Scoring.

PURPOSE:
    Reads all CEP JSON files produced by Phase 3 and produces a JSONL file
    (metrics.jsonl) where every line is a scored evaluation row.

    For each CEP this script extracts:
        - evaluator_verdict   : raw verdict from EvaluatorAgent
        - verifier_verdict    : "confirmed" | "revised" | "skipped"
        - final_verdict       : verifier-adjusted verdict (or evaluator's if skipped)
        - compliance_score    : 1.0 compliant / 0.5 partial / 0.0 non_compliant / None NA
        - confidence          : EvaluatorAgent's self-reported confidence (0–1)
        - evidence_quality    : "strong" | "moderate" | "weak" | "absent"
        - gap_description     : text description of any compliance gap
        - latency_sec         : planner + evaluator wall-clock time

    Then (unless --no_judge) it calls an LLM judge over each CEP and appends
    5 rubric scores per row:
        judge_evidence_quality       : 0–1
        judge_verdict_accuracy       : 0–1
        judge_gap_clarity            : 0–1
        judge_evidence_traceability  : 0–1
        judge_reasoning_soundness    : 0–1

PASTE TO:
    <repo-root>/implementations/caiq_procurement_eval/execution/phase4/run_eval.py

RUN WITH (from repo root):
    # With LLM judge (default):
    uv run --env-file .env --group caiq-procurement-eval \
        python implementations/caiq_procurement_eval/execution/phase4/run_eval.py \
        --cep_dir implementations/caiq_procurement_eval/execution/phase3/ceps/gemini_gemini/ \
        --out implementations/caiq_procurement_eval/execution/phase4/output/metrics.jsonl

    # Without LLM judge (faster, cheaper):
    uv run --env-file .env --group caiq-procurement-eval \
        python implementations/caiq_procurement_eval/execution/phase4/run_eval.py \
        --cep_dir implementations/caiq_procurement_eval/execution/phase3/ceps/gemini_gemini/ \
        --out implementations/caiq_procurement_eval/execution/phase4/output/metrics.jsonl \
        --no_judge

WHAT TO CHECK AFTER RUNNING:
    1. Terminal shows each sample_id → final_verdict (evidence_quality)
    2. output/metrics.jsonl contains one JSON line per CEP
    3. Each line has compliance_score, final_verdict, and (if judge enabled) judge_* scores
    4. Green light: proceed to Phase 5 for aggregation and reporting
"""

import argparse
import sys
from pathlib import Path


def main() -> None:
    """Parse args and run CEP evaluation."""
    parser = argparse.ArgumentParser(description="Phase 4 — Evaluate CEPs with verdicts + LLM judge")
    parser.add_argument(
        "--cep_dir",
        required=True,
        help="Directory containing CEP JSON files (from Phase 3 output)",
    )
    parser.add_argument(
        "--out",
        default="implementations/caiq_procurement_eval/execution/phase4/output/metrics.jsonl",
        help="Output JSONL file path",
    )
    parser.add_argument("--no_judge", action="store_true", help="Skip LLM-as-judge scoring (faster)")
    parser.add_argument(
        "--judge_backend",
        default="gemini",
        choices=["gemini", "openai"],
        help="Model backend for judge (default: gemini)",
    )
    parser.add_argument(
        "--judge_model",
        default="gemini-2.5-flash-lite",
        help="Model name for judge (default: gemini-2.5-flash-lite)",
    )
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    cep_dir = Path(args.cep_dir)
    if not cep_dir.exists():
        print(f"  [FAIL] CEP directory not found: {cep_dir}")
        print(f"         Run Phase 3 first to generate CEPs.")
        sys.exit(1)

    cep_count = len(list(cep_dir.glob("*.json")))
    if cep_count == 0:
        print(f"  [FAIL] No CEP JSON files found in {cep_dir}")
        sys.exit(1)

    print(f"\n=== Phase 4: CEP Evaluation ===\n")
    print(f"  CEP directory : {cep_dir}  ({cep_count} files)")
    print(f"  Output file   : {args.out}")
    print(f"  LLM judge     : {'disabled' if args.no_judge else f'enabled ({args.judge_backend}/{args.judge_model})'}")
    print()

    # Delegate to the package evaluator
    from caiq_procurement_eval.eval.eval_outputs import evaluate_cep_dir

    evaluate_cep_dir(
        cep_dir=str(cep_dir),
        out_file=args.out,
        no_judge=args.no_judge,
        judge_backend=args.judge_backend,
        judge_model=args.judge_model,
    )

    print(f"\n  -> Open {args.out} and inspect verdict + score distribution.")
    print("  -> Green light: proceed to Phase 5.")


if __name__ == "__main__":
    main()
