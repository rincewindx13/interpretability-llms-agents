"""EvaluatorAgent — reads vendor evidence and produces a compliance verdict.

Equivalent to the VisionAgent in agentic_vqa_eval: it executes the plan
by analysing the vendor's CAIQ answer and comment against the CCM control.
"""

import os
from pathlib import Path
from typing import Any, List, Optional, Tuple

from crewai import LLM, Agent, Crew, Task

from ..datasets.caiq_sample import CAIQSample
from ..langfuse_integration.tracing import close_span, open_llm_span
from ..utils.json_strict import parse_strict


EVALUATOR_PROMPT_PATH = Path(__file__).parent / "prompts" / "evaluator.txt"

VERDICT_REQUIRED_KEYS = [
    "verdict",
    "confidence",
    "evidence_quality",
    "gap_description",
    "evidence_citation",
    "reasoning",
]

_FALLBACK_VERDICT = {
    "verdict": "needs_clarification",
    "confidence": 0.0,
    "evidence_quality": "absent",
    "gap_description": "Evaluation failed — no verdict produced.",
    "evidence_citation": "",
    "recommended_followup": "",
    "reasoning": "Evaluator agent failed to produce a verdict.",
}


def _load_template() -> str:
    return EVALUATOR_PROMPT_PATH.read_text(encoding="utf-8")


def build_evaluator_prompt(sample: CAIQSample, plan: dict, ccm_context: Optional[str] = None) -> str:
    """Inject sample and plan details into the evaluator prompt template."""
    template = _load_template()
    steps = plan.get("steps", [])
    steps_text = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(steps)) or "  (none)"

    ccm_block = ""
    if ccm_context:
        ccm_block = f"CCM Control Context:\n{ccm_context}"

    return template.format(
        question_id=sample.question_id,
        control_id=sample.control_id,
        question_text=sample.question_text,
        vendor_answer=sample.vendor_answer.value,
        vendor_comment=sample.vendor_comment or "(no evidence provided)",
        plan_steps=steps_text,
        expected_evidence_type=plan.get("expected_evidence_type", ""),
        evaluation_focus=plan.get("evaluation_focus", ""),
        ccm_context_block=ccm_block,
    )


def _build_llm(backend: str, model: str, api_key: Optional[str]) -> LLM:
    if backend == "openai":
        return LLM(
            model=model,
            api_key=api_key or os.environ.get("OPENAI_API_KEY", ""),
            temperature=0,
        )
    if backend == "gemini":
        return LLM(
            model=f"gemini/{model}",
            api_key=api_key or os.environ.get("GEMINI_API_KEY", ""),
            temperature=0,
        )
    raise ValueError(f"Unknown evaluator backend: {backend!r}")


class EvaluatorAgent:
    """Reads vendor CAIQ evidence and produces a structured compliance verdict.

    Follows the evaluation plan produced by the PlannerAgent and returns
    a verdict with evidence citations and gap descriptions for full traceability.
    """

    def __init__(
        self,
        backend: str = "gemini",
        model: str = "gemini-2.5-flash-lite",
        api_key: Optional[str] = None,
    ):
        self.backend = backend
        self.model = model
        self.api_key = api_key
        self._llm = _build_llm(backend, model, api_key)

    def run(
        self,
        sample: CAIQSample,
        plan: dict,
        lf_trace: Any = None,
        ccm_context: Optional[str] = None,
    ) -> Tuple[str, dict, bool, str, List[dict]]:
        """Execute the evaluation phase for a single CAIQ sample.

        Returns
        -------
        prompt : str
        parsed : dict
        parse_error : bool
        raw_text : str
        tool_traces : list of dict
        """
        prompt = build_evaluator_prompt(sample, plan, ccm_context)

        span = open_llm_span(
            lf_trace,
            name="evaluator",
            input_data={"prompt": prompt},
            model=self.model,
            metadata={"backend": self.backend, "vendor": sample.vendor, "question_id": sample.question_id},
        )

        agent = Agent(
            role="Cloud Security Compliance Auditor",
            goal=(
                "Produce a precise JSON compliance verdict for a vendor's CAIQ response. "
                "Output JSON only — no extra text."
            ),
            backstory=(
                "You are a certified cloud security auditor. You evaluate vendor responses to "
                "CSA CAIQ questions by analysing the evidence quality, checking for gaps, "
                "and producing fully traceable compliance verdicts grounded in the vendor's text."
            ),
            llm=self._llm,
            verbose=False,
            allow_delegation=False,
        )

        task = Task(
            description=prompt,
            expected_output=(
                "A JSON object with keys: verdict, confidence, evidence_quality, "
                "gap_description, evidence_citation, recommended_followup, reasoning"
            ),
            agent=agent,
        )

        crew = Crew(agents=[agent], tasks=[task], verbose=False)
        result = crew.kickoff()

        raw_text: str = getattr(result, "raw", None) or str(result)
        parsed, parse_ok = parse_strict(raw_text, required_keys=VERDICT_REQUIRED_KEYS)

        if not parsed:
            parsed = dict(_FALLBACK_VERDICT)

        close_span(
            span,
            output={"verdict": parsed.get("verdict", ""), "parse_error": not parse_ok},
        )

        return prompt, parsed, not parse_ok, raw_text, []
