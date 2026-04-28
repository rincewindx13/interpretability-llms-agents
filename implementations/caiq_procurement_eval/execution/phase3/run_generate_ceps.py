"""Phase 3 — Generate Compliance Evaluation Packets (CEPs).

PURPOSE:
    Runs the full three-agent pipeline on every CAIQ sample:

        PlannerAgent   → analyses the question, identifies CCM domain risk,
                          plans evaluation steps (text-only, no vendor data)
        EvaluatorAgent → reads vendor answer + optional CCM context,
                          produces verdict + evidence quality score
        VerifierAgent  → cross-checks evaluator's verdict (Pass 2.5)

    Each sample produces one CEP JSON file written to --out/.
    CEPs are the portable trace artifacts used in Phase 4 (judge scoring)
    and Phase 5 (compliance reporting).

PASTE TO:
    <repo-root>/implementations/caiq_procurement_eval/execution/phase3/run_generate_ceps.py

RUN WITH (from repo root):
    uv run --env-file .env --group caiq-procurement-eval \
        python implementations/caiq_procurement_eval/execution/phase3/run_generate_ceps.py \
        --dataset_dir /path/to/int-dataset \
        --n 50 \
        --config gemini_gemini \
        --workers 4 \
        --out implementations/caiq_procurement_eval/execution/phase3/ceps/

    # With CCM context lookup (recommended):
    uv run --env-file .env --group caiq-procurement-eval \
        python implementations/caiq_procurement_eval/execution/phase3/run_generate_ceps.py \
        --dataset_dir /path/to/int-dataset \
        --ccm_file /path/to/CCM.xlsx \
        --n 50 \
        --config gemini_gemini \
        --workers 4 \
        --out implementations/caiq_procurement_eval/execution/phase3/ceps/

CONFIGS:
    gemini_gemini  — Planner + Evaluator both use Gemini 2.5 Flash Lite (cheapest)
    openai_openai  — Planner + Evaluator both use GPT-4o
    gemini_openai  — Planner=Gemini, Evaluator=GPT-4o

WHAT TO CHECK AFTER RUNNING:
    1. Terminal shows "[N/total] sample_id → OK → path/to/cep.json"
    2. --out/gemini_gemini/ (or chosen config) folder contains one JSON per sample
    3. Each CEP JSON has: plan, evaluation, verifier, timestamps sections
    4. Langfuse dashboard shows one trace per sample (if keys configured)
    5. Check for ERROR lines — re-run failed samples individually if needed
"""

import argparse
import sys
from pathlib import Path


def main() -> None:
    """Parse args and delegate to the caiq_procurement_eval runner."""
    parser = argparse.ArgumentParser(description="Phase 3 — Generate CEPs for CAIQ vendor assessments")
    parser.add_argument("--dataset_dir", required=True, help="Directory containing CAIQ .xlsx files")
    parser.add_argument("--ccm_file", default=None, help="Path to CCM .xlsx file (optional — adds control context)")
    parser.add_argument("--vendors", nargs="*", default=None, help="Vendor name substrings to include (default: all)")
    parser.add_argument("--n", type=int, default=50, help="Max questions per vendor")
    parser.add_argument(
        "--config",
        default="gemini_gemini",
        choices=["gemini_gemini", "openai_openai", "gemini_openai"],
        help="Backend config (planner_evaluator)",
    )
    parser.add_argument("--workers", type=int, default=2, help="Parallel workers (keep ≤ 5 for rate limits)")
    parser.add_argument(
        "--out",
        default="implementations/caiq_procurement_eval/execution/phase3/ceps/",
        help="Output directory for CEP JSON files",
    )
    parser.add_argument("--no_verifier", action="store_true", help="Skip VerifierAgent (Pass 2.5)")
    parser.add_argument("--no_ccm", action="store_true", help="Skip CCM context lookup even if --ccm_file given")
    parser.add_argument("--planner_model", default=None, help="Override planner model name")
    parser.add_argument("--evaluator_model", default=None, help="Override evaluator model name")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    print(f"\n=== Phase 3: CEP Generation ===\n")
    print(f"  Dataset dir  : {args.dataset_dir}")
    print(f"  Config       : {args.config}")
    print(f"  Max per vendor: {args.n}")
    print(f"  Workers      : {args.workers}")
    print(f"  Output dir   : {args.out}")
    print(f"  Verifier     : {'disabled' if args.no_verifier else 'enabled'}")
    print(f"  CCM file     : {args.ccm_file or 'not provided'}")
    print()

    # Delegate to the package runner — reuse all production logic
    from caiq_procurement_eval.runner.run_generate_ceps import main as runner_main

    # Reconstruct sys.argv so argparse inside runner_main sees our flags
    sys.argv = ["run_generate_ceps"]
    sys.argv += ["--dataset_dir", args.dataset_dir]
    sys.argv += ["--n", str(args.n)]
    sys.argv += ["--config", args.config]
    sys.argv += ["--workers", str(args.workers)]
    sys.argv += ["--out", args.out]
    if args.no_verifier:
        sys.argv += ["--no_verifier"]
    if args.ccm_file:
        sys.argv += ["--ccm_file", args.ccm_file]
    if args.no_ccm:
        sys.argv += ["--no_ccm"]
    if args.vendors:
        sys.argv += ["--vendors"] + args.vendors
    if args.planner_model:
        sys.argv += ["--planner_model", args.planner_model]
    if args.evaluator_model:
        sys.argv += ["--evaluator_model", args.evaluator_model]

    runner_main()

    print("\n  -> Review CEP JSON files in the output directory.")
    print("  -> Check for any ERROR lines above and re-run if needed.")
    print("  -> Green light: proceed to Phase 4.")


if __name__ == "__main__":
    main()
