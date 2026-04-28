"""VerifierAgent — independently cross-checks the evaluator's compliance verdict.

Equivalent to the VerifierAgent (Pass 2.5) in agentic_vqa_eval: it re-reads
the vendor evidence and confirms or revises the draft verdict.
"""

import os
from typing import Any, Optional, Tuple

from crewai import LLM, Agent, Crew, Task

from ..datasets.caiq_sample import CAIQSample
from ..langfuse_integration.tracing import close_span, open_llm_span
from ..utils.json_strict import parse_strict


_VERIFIER_PROMPT = """\
You are an independent cloud security compliance reviewer.

A compliance evaluator has assessed the following vendor CAIQ response and produced a draft verdict.
Your job is to independently re-examine the evidence and either CONFIRM or REVISE the verdict.

CAIQ Question ID : {question_id}
CCM Control ID   : {control_id}
Question Text    : {question_text}
Vendor Answer    : {vendor_answer}
Vendor Evidence  : {vendor_comment}

Draft Verdict    : {draft_verdict}
Draft Reasoning  : {draft_reasoning}
Evidence Quality : {draft_evidence_quality}

Re-examine the vendor's evidence independently. Then produce a JSON response:

{{
  "verdict": "<confirmed | revised>",
  "final_verdict": "<compliant | non_compliant | partial | not_applicable | needs_clarification>",
  "reasoning": "<one sentence: why you confirmed or what you changed and why>"
}}

Output ONLY valid JSON — no markdown, no extra text.
"""

VERIFIER_REQUIRED_KEYS = ["verdict", "final_verdict", "reasoning"]


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
    raise ValueError(f"Unknown verifier backend: {backend!r}")


class VerifierAgent:
    """Independently re-examines vendor evidence and confirms or revises the verdict.

    Runs as Pass 2.5 — after the EvaluatorAgent but before the CEP is written.
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
        evaluation: dict,
        lf_trace: Any = None,
    ) -> Tuple[str, dict, bool, str]:
        """Cross-check the evaluator's verdict against vendor evidence.

        Returns
        -------
        prompt : str
        parsed : dict
        parse_error : bool
        raw_text : str
        """
        prompt = _VERIFIER_PROMPT.format(
            question_id=sample.question_id,
            control_id=sample.control_id,
            question_text=sample.question_text,
            vendor_answer=sample.vendor_answer.value,
            vendor_comment=sample.vendor_comment or "(no evidence provided)",
            draft_verdict=evaluation.get("verdict", ""),
            draft_reasoning=evaluation.get("reasoning", ""),
            draft_evidence_quality=evaluation.get("evidence_quality", ""),
        )

        span = open_llm_span(
            lf_trace,
            name="verifier",
            input_data={"prompt": prompt},
            model=self.model,
            metadata={"backend": self.backend},
        )

        agent = Agent(
            role="Independent Compliance Reviewer",
            goal=(
                "Independently verify a compliance verdict against vendor evidence. "
                "Output JSON only — no extra text."
            ),
            backstory=(
                "You are a senior cloud security reviewer performing a second-pass audit. "
                "You re-read the vendor's evidence without bias and confirm or revise the verdict."
            ),
            llm=self._llm,
            verbose=False,
            allow_delegation=False,
        )

        task = Task(
            description=prompt,
            expected_output="A JSON object with keys: verdict, final_verdict, reasoning",
            agent=agent,
        )

        crew = Crew(agents=[agent], tasks=[task], verbose=False)
        result = crew.kickoff()

        raw_text: str = getattr(result, "raw", None) or str(result)
        parsed, parse_ok = parse_strict(raw_text, required_keys=VERIFIER_REQUIRED_KEYS)

        if not parsed:
            parsed = {
                "verdict": "confirmed",
                "final_verdict": evaluation.get("verdict", "needs_clarification"),
                "reasoning": "Verifier could not parse output — original verdict retained.",
            }

        close_span(
            span,
            output={"verifier_verdict": parsed.get("verdict", ""), "parse_error": not parse_ok},
        )

        return prompt, parsed, not parse_ok, raw_text
