"""PlannerAgent — maps a CAIQ question to a structured compliance evaluation strategy.

The planner receives the question, control ID, domain, and vendor answer type
and produces a JSON plan that the EvaluatorAgent will follow.
"""

import os
from pathlib import Path
from typing import Any, Optional, Tuple

from crewai import LLM, Agent, Crew, Task

from ..datasets.caiq_sample import CAIQSample
from ..langfuse_integration.tracing import close_span, open_llm_span
from ..utils.json_strict import parse_strict


PLANNER_PROMPT_PATH = Path(__file__).parent / "prompts" / "planner.txt"

PLAN_REQUIRED_KEYS = [
    "steps",
    "expected_evidence_type",
    "compliance_risk_level",
    "evaluation_focus",
    "nist_mapping_hint",
    "answerability_check",
]

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


def _load_template() -> str:
    return PLANNER_PROMPT_PATH.read_text(encoding="utf-8")


def build_planner_prompt(sample: CAIQSample) -> str:
    """Inject sample details into the planner prompt template."""
    template = _load_template()
    return template.format(
        question_id=sample.question_id,
        control_id=sample.control_id,
        domain_id=sample.domain_id,
        question_text=sample.question_text,
        vendor_answer=sample.vendor_answer.value,
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
    raise ValueError(f"Unknown planner backend: {backend!r}")


class PlannerAgent:
    """Derives a structured compliance evaluation strategy for a CAIQ question.

    Text-only — does not read vendor evidence. Produces a JSON plan that
    specifies what steps the EvaluatorAgent should follow, what evidence
    to look for, and how critical a gap would be.
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

    def run(self, sample: CAIQSample, lf_trace: Any = None) -> Tuple[str, dict, bool, str]:
        """Execute the planning phase for a single CAIQ sample.

        Returns
        -------
        prompt : str
        parsed : dict
        parse_error : bool
        raw_text : str
        """
        prompt = build_planner_prompt(sample)

        span = open_llm_span(
            lf_trace,
            name="planner",
            input_data={"prompt": prompt},
            model=self.model,
            metadata={"backend": self.backend},
        )

        agent = Agent(
            role="Compliance Evaluation Planner",
            goal=(
                "Produce a precise JSON evaluation plan for assessing a vendor's CAIQ response. "
                "Output JSON only — no extra text."
            ),
            backstory=(
                "You are a senior cloud security auditor specialising in the CSA Cloud Controls Matrix. "
                "You design structured evaluation procedures without reading the vendor evidence, "
                "so the evaluator agent can follow your plan precisely."
            ),
            llm=self._llm,
            verbose=False,
            allow_delegation=False,
        )

        task = Task(
            description=prompt,
            expected_output=(
                "A JSON object with keys: steps (list of 2-4 strings), "
                "expected_evidence_type, compliance_risk_level, evaluation_focus, "
                "nist_mapping_hint, answerability_check"
            ),
            agent=agent,
        )

        crew = Crew(agents=[agent], tasks=[task], verbose=False)
        result = crew.kickoff()

        raw_text: str = getattr(result, "raw", None) or str(result)
        parsed, parse_ok = parse_strict(raw_text, required_keys=PLAN_REQUIRED_KEYS)

        if parsed and "steps" in parsed:
            steps = list(parsed["steps"])
            if len(steps) < 2:
                steps += ["Verify evidence supports the stated answer"] * (2 - len(steps))
            parsed["steps"] = steps[:4]

        if not parsed:
            parsed = dict(_FALLBACK_PLAN)

        close_span(
            span,
            output={"plan_steps": parsed.get("steps", []), "parse_error": not parse_ok},
        )

        return prompt, parsed, not parse_ok, raw_text
