"""Pass 1 evaluation — compliance verdict accuracy and LLM judge scoring."""

import argparse
import json
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .judge import judge_cep
from ..cep.writer import iter_ceps
from ..langfuse_integration.client import get_client
from ..langfuse_integration.tracing import log_trace_scores


load_dotenv()

_VERDICT_MAP = {
    "compliant": 1.0,
    "partial": 0.5,
    "not_applicable": None,
    "non_compliant": 0.0,
    "needs_clarification": 0.0,
}


def evaluate_cep_dir(
    cep_dir: str,
    out_file: str,
    no_judge: bool = False,
    judge_backend: str = "gemini",
    judge_model: str = "gemini-2.5-flash-lite",
    api_key: Optional[str] = None,
) -> None:
    """Evaluate all CEPs in a directory and write metrics to a JSONL file.

    Parameters
    ----------
    cep_dir : str
        Directory containing CEP JSON files.
    out_file : str
        Output JSONL file path.
    no_judge : bool
        If True, skip LLM-as-judge scoring.
    judge_backend : str
        Model provider for judging.
    judge_model : str
        Model name for judging.
    api_key : str, optional
        Provider API key.
    """
    lf_client = get_client()
    out_path = Path(out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as fout:
        for cep in iter_ceps(cep_dir):
            sample = cep.get("sample", {})
            evaluation = cep.get("evaluation", {}).get("parsed", {})
            verifier = cep.get("verifier")
            timestamps = cep.get("timestamps", {})

            sample_id = sample.get("sample_id", "")
            vendor = sample.get("vendor", "")
            question_id = sample.get("question_id", "")
            vendor_answer = sample.get("vendor_answer", "")
            domain_id = sample.get("domain_id", "")

            verdict = evaluation.get("verdict", "needs_clarification")
            confidence = evaluation.get("confidence", 0.0)
            evidence_quality = evaluation.get("evidence_quality", "absent")

            verifier_verdict = "skipped"
            final_verdict = verdict
            if verifier:
                verifier_verdict = verifier.get("verdict", "skipped")
                if verifier_verdict == "revised":
                    final_verdict = verifier.get("parsed", {}).get("final_verdict", verdict)

            compliance_score = _VERDICT_MAP.get(final_verdict)

            row = {
                "sample_id": sample_id,
                "vendor": vendor,
                "question_id": question_id,
                "domain_id": domain_id,
                "vendor_answer": vendor_answer,
                "evaluator_verdict": verdict,
                "verifier_verdict": verifier_verdict,
                "final_verdict": final_verdict,
                "compliance_score": compliance_score,
                "confidence": confidence,
                "evidence_quality": evidence_quality,
                "gap_description": evaluation.get("gap_description", ""),
                "evidence_citation": evaluation.get("evidence_citation", ""),
                "latency_sec": (timestamps.get("evaluator_ms", 0) + timestamps.get("planner_ms", 0)) / 1000.0,
                "lf_trace_id": cep.get("lf_trace_id"),
            }

            if not no_judge:
                scores = judge_cep(cep, backend=judge_backend, model=judge_model, api_key=api_key)
                for k, v in scores.items():
                    row[f"judge_{k}"] = v

                if lf_client and cep.get("lf_trace_id"):
                    log_trace_scores(None, scores)

            fout.write(json.dumps(row) + "\n")
            print(f"  {sample_id} → {final_verdict} ({evidence_quality})")

    print(f"\nMetrics written to: {out_file}")


def main() -> None:
    """CLI entry point for Pass 1 evaluation."""
    parser = argparse.ArgumentParser(description="Evaluate CEPs — compliance verdicts + judge")
    parser.add_argument("--cep_dir", required=True, help="Directory containing CEP JSON files")
    parser.add_argument("--out", default="output/metrics.jsonl", help="Output JSONL file")
    parser.add_argument("--no_judge", action="store_true", help="Skip LLM judge scoring")
    parser.add_argument("--judge_backend", default="gemini")
    parser.add_argument("--judge_model", default="gemini-2.5-flash-lite")
    args = parser.parse_args()

    evaluate_cep_dir(
        cep_dir=args.cep_dir,
        out_file=args.out,
        no_judge=args.no_judge,
        judge_backend=args.judge_backend,
        judge_model=args.judge_model,
    )


if __name__ == "__main__":
    main()
