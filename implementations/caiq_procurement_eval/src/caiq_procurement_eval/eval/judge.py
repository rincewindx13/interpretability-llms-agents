"""LLM-as-judge evaluator for CEP compliance verdicts.

Scores five rubric dimensions (0.0–1.0) focused on interpretability:
evidence quality, verdict accuracy, gap clarity, traceability, and reasoning.
"""

import os
from typing import Optional

from google import genai
from openai import OpenAI

from ..utils.json_strict import parse_strict


_JUDGE_PROMPT = """\
You are an expert cloud security compliance auditor evaluating the quality of an AI agent's compliance verdict.

CAIQ Question     : {question_text}
CCM Control ID    : {control_id}
Vendor            : {vendor}
Vendor Answer     : {vendor_answer}
Vendor Evidence   : {vendor_comment}

Agent Verdict         : {agent_verdict}
Agent Reasoning       : {agent_reasoning}
Agent Evidence Citation: {agent_evidence_citation}
Agent Gap Description : {agent_gap_description}

Evaluation plan the agent should have followed:
{plan_steps}

Score each dimension from 0.0 to 1.0:

1. evidence_quality      — Does the agent accurately assess the quality of the vendor's evidence?
2. verdict_accuracy      — Is the compliance verdict (compliant/non_compliant/partial) correct given the evidence?
3. gap_clarity           — Is the gap description specific and actionable for the procurement team?
4. evidence_traceability — Does the evidence citation directly quote or reference the vendor's text?
5. reasoning_soundness   — Does the reasoning logically connect the evidence to the verdict?

Output ONLY JSON, no markdown, no extra text:
{{
  "evidence_quality": 0.0,
  "verdict_accuracy": 0.0,
  "gap_clarity": 0.0,
  "evidence_traceability": 0.0,
  "reasoning_soundness": 0.0,
  "reasoning": "<one-sentence rationale>"
}}"""

_JUDGE_KEYS = [
    "evidence_quality",
    "verdict_accuracy",
    "gap_clarity",
    "evidence_traceability",
    "reasoning_soundness",
]


def _default_scores() -> dict:
    return dict.fromkeys(_JUDGE_KEYS, 0.0)


def _call_llm(prompt: str, backend: str, model: str, api_key: Optional[str]) -> str:
    if backend == "openai":
        client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY", ""))
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_completion_tokens=512,
        )
        return resp.choices[0].message.content or ""

    if backend == "gemini":
        client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY", ""))
        resp = client.models.generate_content(model=model, contents=prompt)
        return resp.text or ""

    raise ValueError(f"Unknown judge backend: {backend!r}")


def judge_cep(
    cep: dict,
    backend: str = "gemini",
    model: str = "gemini-2.5-flash-lite",
    api_key: Optional[str] = None,
) -> dict:
    """Score the interpretability quality of a single CEP.

    Parameters
    ----------
    cep : dict
        The compliance evaluation packet to judge.
    backend : str
        Model provider — 'openai' or 'gemini'.
    model : str
        Model name.
    api_key : str, optional
        Provider API key.

    Returns
    -------
    dict
        Rubric scores and reasoning.
    """
    sample = cep.get("sample", {})
    plan = cep.get("plan", {}).get("parsed", {})
    evaluation = cep.get("evaluation", {}).get("parsed", {})

    plan_steps = plan.get("steps", [])
    steps_text = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(plan_steps)) or "  (none)"

    prompt = _JUDGE_PROMPT.format(
        question_text=sample.get("question_text", ""),
        control_id=sample.get("control_id", ""),
        vendor=sample.get("vendor", ""),
        vendor_answer=sample.get("vendor_answer", ""),
        vendor_comment=sample.get("vendor_comment", ""),
        agent_verdict=evaluation.get("verdict", ""),
        agent_reasoning=evaluation.get("reasoning", ""),
        agent_evidence_citation=evaluation.get("evidence_citation", ""),
        agent_gap_description=evaluation.get("gap_description", ""),
        plan_steps=steps_text,
    )

    try:
        raw = _call_llm(prompt, backend, model, api_key)
        scores, ok = parse_strict(raw, required_keys=_JUDGE_KEYS)
        if not scores:
            scores = _default_scores()
            scores["judge_parse_error"] = True
        return scores
    except Exception as exc:
        s = _default_scores()
        s["judge_error"] = str(exc)
        return s
