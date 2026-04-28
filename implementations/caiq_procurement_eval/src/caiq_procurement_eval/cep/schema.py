"""Compliance Evaluation Packet (CEP) schema — portable trace artifact.

CEP v1 stores everything needed to replay and audit a single vendor
compliance assessment against a CAIQ question.
"""

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CEPConfig:
    """Configuration of the agent run, including backend and model choices."""

    planner_backend: str
    evaluator_backend: str
    judge_backend: str
    config_name: str
    planner_model: str
    evaluator_model: str


@dataclass
class CEPSample:
    """Metadata about the CAIQ question and vendor assessment."""

    vendor: str
    sample_id: str
    question_id: str
    control_id: str
    domain_id: str
    question_text: str
    vendor_answer: str
    vendor_comment: str
    caiq_version: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CEPPlan:
    """The planner agent's compliance evaluation strategy.

    Captures what CCM control the question maps to, how to interpret
    the vendor's answer, and what evidence to look for.
    """

    prompt: str
    raw_text: str
    parsed: Dict[str, Any] = field(default_factory=dict)
    parse_error: bool = False


@dataclass
class ToolTrace:
    """Trace of a single tool call made by the agent."""

    tool: str
    backend: str
    model: str
    start_ts: str
    end_ts: str
    elapsed_ms: float = 0.0
    provider_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CEPEvaluation:
    """The evaluator agent's compliance verdict.

    Reads the vendor answer + evidence and produces a structured verdict.
    """

    prompt: str
    raw_text: str
    parsed: Dict[str, Any] = field(default_factory=dict)
    parse_error: bool = False
    tool_trace: List[Dict] = field(default_factory=list)


@dataclass
class CEPVerifier:
    """The verifier agent's cross-check of the evaluation verdict.

    Independently re-reads vendor evidence and confirms or revises the verdict.
    """

    prompt: str
    raw_text: str
    parsed: Dict[str, Any] = field(default_factory=dict)
    parse_error: bool = False
    verdict: str = "skipped"  # "confirmed" | "revised" | "skipped"


@dataclass
class CEPTimestamps:
    """Wall-clock timing for each pipeline stage."""

    start: str
    end: str
    planner_ms: float = 0.0
    evaluator_ms: float = 0.0
    verifier_ms: float = 0.0


@dataclass
class CEP:
    """Complete Compliance Evaluation Packet for a single CAIQ question-answer pair.

    Contains everything needed to replay, audit, and explain every compliance
    verdict: the planner strategy, the evaluator's reading of vendor evidence,
    the verifier's cross-check, timing, and any errors.
    """

    schema_version: str = "cep.v1"
    run_id: str = ""
    config: Optional[CEPConfig] = None
    sample: Optional[CEPSample] = None
    plan: Optional[CEPPlan] = None
    evaluation: Optional[CEPEvaluation] = None
    verifier: Optional[CEPVerifier] = None
    timestamps: Optional[CEPTimestamps] = None
    errors: List[str] = field(default_factory=list)
    lf_trace_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Return a dict representation suitable for JSON serialisation."""
        return dataclasses.asdict(self)
