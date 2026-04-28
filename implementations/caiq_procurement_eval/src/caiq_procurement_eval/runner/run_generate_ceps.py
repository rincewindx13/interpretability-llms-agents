r"""Runner: generate Compliance Evaluation Packets (CEPs) for CAIQ vendor assessments.

Usage:
    uv run --env-file .env -m caiq_procurement_eval.runner.run_generate_ceps \
        --dataset_dir path/to/int-dataset \
        --n 50 \
        --config gemini_gemini \
        --workers 4 \
        --out ceps/
"""

import argparse
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from ..agents.evaluator_agent import EvaluatorAgent
from ..agents.planner_agent import PlannerAgent
from ..agents.verifier_agent import VerifierAgent
from ..cep.schema import (
    CEP,
    CEPConfig,
    CEPEvaluation,
    CEPPlan,
    CEPSample,
    CEPTimestamps,
    CEPVerifier,
)
from ..cep.writer import write_cep
from ..datasets.caiq_loader import load_caiq_directory, load_caiq_file
from ..datasets.caiq_sample import CAIQSample
from ..langfuse_integration.client import get_client
from ..langfuse_integration.tracing import log_trace_scores, sample_trace
from ..tools.ccm_lookup_tool import CCMLookupTool
from ..utils.timing import iso_now, timed


load_dotenv()

BACKEND_CONFIGS: dict = {
    "gemini_gemini": {
        "planner_backend": "gemini",
        "planner_model": "gemini-2.5-flash",
        "evaluator_backend": "gemini",
        "evaluator_model": "gemini-2.5-flash",
        "judge_backend": "gemini",
    },
    "openai_openai": {
        "planner_backend": "openai",
        "planner_model": "gpt-4o",
        "evaluator_backend": "openai",
        "evaluator_model": "gpt-4o",
        "judge_backend": "openai",
    },
    "gemini_openai": {
        "planner_backend": "gemini",
        "planner_model": "gemini-2.5-flash-lite",
        "evaluator_backend": "openai",
        "evaluator_model": "gpt-4o",
        "judge_backend": "gemini",
    },
}

_FALLBACK_PLAN = {
    "steps": [
        "Identify the CCM control domain and its compliance requirements",
        "Assess whether the vendor's answer is consistent with the question intent",
        "Evaluate the quality and specificity of the vendor's evidence",
    ],
    "expected_evidence_type": "policy document or process description",
    "compliance_risk_level": "medium",
    "evaluation_focus": "presence and specificity of supporting evidence",
    "nist_mapping_hint": "unknown",
    "answerability_check": "answerable",
}


def process_sample(
    sample: CAIQSample,
    planner: PlannerAgent,
    evaluator: EvaluatorAgent,
    config: dict,
    run_id: str,
    out_dir: str,
    lf_client=None,
    verifier: Optional[VerifierAgent] = None,
    ccm_tool: Optional[CCMLookupTool] = None,
) -> str:
    """Execute the full CEP pipeline for a single CAIQ sample.

    Returns
    -------
    str
        Absolute path of the written CEP file.
    """
    config_name = f"{config['planner_backend']}_{config['evaluator_backend']}"
    run_start = iso_now()
    errors: list = []

    with sample_trace(
        lf_client,
        sample_id=sample.sample_id,
        question=sample.question_text,
        expected_output=sample.vendor_answer.value,
        question_type=sample.domain_id,
        config_name=config_name,
        run_id=run_id,
    ) as lf_trace:
        lf_trace_id = getattr(lf_trace, "id", None)

        # ---- Planner ----
        plan_prompt, plan_parsed, plan_parse_error, plan_raw = "", {}, True, ""
        plan_ms = 0.0
        try:
            with timed() as pt:
                plan_prompt, plan_parsed, plan_parse_error, plan_raw = planner.run(sample, lf_trace=lf_trace)
            plan_ms = pt.elapsed_ms
        except Exception as exc:
            errors.append(f"planner_error: {exc}")
            plan_parsed = dict(_FALLBACK_PLAN)
            traceback.print_exc()

        # ---- CCM context lookup (optional) ----
        ccm_context: Optional[str] = None
        if ccm_tool:
            ccm_context = ccm_tool.lookup(sample.control_id)

        # ---- Evaluator ----
        eval_prompt, eval_parsed, eval_parse_error, eval_raw, eval_traces = "", {}, True, "", []
        eval_ms = 0.0
        try:
            with timed() as et:
                eval_prompt, eval_parsed, eval_parse_error, eval_raw, eval_traces = evaluator.run(
                    sample, plan_parsed, lf_trace=lf_trace, ccm_context=ccm_context
                )
            eval_ms = et.elapsed_ms
        except Exception as exc:
            errors.append(f"evaluator_error: {exc}")
            eval_parsed = {"verdict": "needs_clarification", "reasoning": str(exc)}
            traceback.print_exc()

        # ---- Verifier (Pass 2.5) ----
        verifier_prompt, verifier_parsed, verifier_parse_error, verifier_raw = "", {}, False, ""
        verifier_ms = 0.0
        verifier_verdict = "skipped"

        if verifier is not None:
            try:
                with timed() as vrt:
                    verifier_prompt, verifier_parsed, verifier_parse_error, verifier_raw = verifier.run(
                        sample, plan_parsed, eval_parsed, lf_trace=lf_trace
                    )
                verifier_ms = vrt.elapsed_ms
                verifier_verdict = verifier_parsed.get("verdict", "confirmed")
            except Exception as exc:
                errors.append(f"verifier_error: {exc}")
                verifier_parsed = {"verdict": "confirmed", "final_verdict": eval_parsed.get("verdict", ""), "reasoning": str(exc)}
                verifier_verdict = "confirmed"
                traceback.print_exc()

        run_end = iso_now()

        # ---- Assemble CEP ----
        cep = CEP(
            run_id=run_id,
            config=CEPConfig(
                planner_backend=config["planner_backend"],
                evaluator_backend=config["evaluator_backend"],
                judge_backend=config.get("judge_backend", config["planner_backend"]),
                config_name=config_name,
                planner_model=config["planner_model"],
                evaluator_model=config["evaluator_model"],
            ),
            sample=CEPSample(
                vendor=sample.vendor,
                sample_id=sample.sample_id,
                question_id=sample.question_id,
                control_id=sample.control_id,
                domain_id=sample.domain_id,
                question_text=sample.question_text,
                vendor_answer=sample.vendor_answer.value,
                vendor_comment=sample.vendor_comment,
                caiq_version=sample.caiq_version,
                metadata=sample.metadata,
            ),
            plan=CEPPlan(
                prompt=plan_prompt,
                raw_text=plan_raw,
                parsed=plan_parsed,
                parse_error=plan_parse_error,
            ),
            evaluation=CEPEvaluation(
                prompt=eval_prompt,
                raw_text=eval_raw,
                parsed=eval_parsed,
                parse_error=eval_parse_error,
                tool_trace=eval_traces,
            ),
            verifier=CEPVerifier(
                prompt=verifier_prompt,
                raw_text=verifier_raw,
                parsed=verifier_parsed,
                parse_error=verifier_parse_error,
                verdict=verifier_verdict,
            ) if verifier is not None else None,
            timestamps=CEPTimestamps(
                start=run_start,
                end=run_end,
                planner_ms=plan_ms,
                evaluator_ms=eval_ms,
                verifier_ms=verifier_ms,
            ),
            errors=errors,
            lf_trace_id=lf_trace_id,
        )

        log_trace_scores(
            lf_trace,
            {
                "planner_parse_ok": float(not plan_parse_error),
                "evaluator_parse_ok": float(not eval_parse_error),
                "has_errors": float(bool(errors)),
            },
        )

    return write_cep(cep, out_dir)


def main() -> None:
    """Parse CLI arguments and run the CEP generation pipeline."""
    parser = argparse.ArgumentParser(description="Generate CEPs for CAIQ vendor assessments")
    parser.add_argument("--dataset_dir", required=True, help="Directory containing CAIQ xlsx files")
    parser.add_argument("--ccm_file", default=None, help="Path to CCM xlsx file for control context lookup")
    parser.add_argument("--vendors", nargs="*", default=None, help="Vendor name substrings to include")
    parser.add_argument("--n", type=int, default=20, help="Max questions per vendor")
    parser.add_argument("--config", default="gemini_gemini", choices=list(BACKEND_CONFIGS.keys()))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", default="ceps/")
    parser.add_argument("--no_verifier", action="store_true")
    parser.add_argument("--no_ccm", action="store_true", help="Skip CCM context lookup")
    parser.add_argument("--planner_model", default=None)
    parser.add_argument("--evaluator_model", default=None)
    args = parser.parse_args()

    config = dict(BACKEND_CONFIGS[args.config])
    if args.planner_model:
        config["planner_model"] = args.planner_model
    if args.evaluator_model:
        config["evaluator_model"] = args.evaluator_model

    run_id = str(uuid.uuid4())
    config_name = f"{config['planner_backend']}_{config['evaluator_backend']}"
    out_dir = str(Path(args.out) / config_name)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    print(f"Loading CAIQ dataset from: {args.dataset_dir}")
    samples = load_caiq_directory(args.dataset_dir, vendors=args.vendors, n_per_vendor=args.n)
    print(f"Total samples loaded : {len(samples)}")
    print(f"Config               : {args.config}  run_id={run_id}")
    print(f"Output dir           : {out_dir}")

    lf_client = get_client()
    print(f"Langfuse             : {'enabled' if lf_client else 'not configured'}")

    planner = PlannerAgent(backend=config["planner_backend"], model=config["planner_model"])
    evaluator = EvaluatorAgent(backend=config["evaluator_backend"], model=config["evaluator_model"])

    verifier: Optional[VerifierAgent] = None
    if not args.no_verifier:
        verifier = VerifierAgent(backend=config["evaluator_backend"], model=config["evaluator_model"])
        print(f"Verifier             : enabled")
    else:
        print(f"Verifier             : disabled")

    ccm_tool: Optional[CCMLookupTool] = None
    if not args.no_ccm and args.ccm_file:
        ccm_tool = CCMLookupTool(ccm_file=args.ccm_file)
        print(f"CCM lookup           : enabled ({args.ccm_file})")
    print()

    if args.workers <= 1:
        for i, sample in enumerate(samples, 1):
            print(f"[{i}/{len(samples)}] {sample.sample_id} …", end=" ", flush=True)
            try:
                path = process_sample(sample, planner, evaluator, config, run_id, out_dir, lf_client, verifier, ccm_tool)
                print(f"OK → {path}")
            except Exception as exc:
                print(f"ERROR: {exc}")
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            future_to_sample = {
                pool.submit(process_sample, s, planner, evaluator, config, run_id, out_dir, lf_client, verifier, ccm_tool): s
                for s in samples
            }
            for done, future in enumerate(as_completed(future_to_sample), 1):
                s = future_to_sample[future]
                try:
                    path = future.result()
                    print(f"[{done}/{len(samples)}] {s.sample_id} → {path}")
                except Exception as exc:
                    print(f"[{done}/{len(samples)}] {s.sample_id} ERROR: {exc}")

    print(f"\nDone. CEPs written to: {out_dir}")


if __name__ == "__main__":
    main()
