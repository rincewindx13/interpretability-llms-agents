"""Lightweight Langfuse v4 tracing wrappers for the CEP pipeline.

All helpers accept None as the client/trace and become no-ops.
"""

import contextlib
from contextlib import contextmanager
from typing import Optional


try:
    from langfuse import propagate_attributes
except Exception:
    @contextmanager  # type: ignore[misc]
    def propagate_attributes(**_: object):  # type: ignore[misc]
        yield


def _normalize_usage(usage: dict) -> dict:
    normalized: dict = {}
    if "prompt_tokens" in usage:
        normalized["input"] = usage["prompt_tokens"]
    elif "input" in usage:
        normalized["input"] = usage["input"]
    if "completion_tokens" in usage:
        normalized["output"] = usage["completion_tokens"]
    elif "output" in usage:
        normalized["output"] = usage["output"]
    if "total_tokens" in usage:
        normalized["total"] = usage["total_tokens"]
    elif "total" in usage:
        normalized["total"] = usage["total"]
    return normalized or usage


class _TraceHandle:
    def __init__(self, span: object, trace_id: Optional[str]) -> None:
        self._span = span
        self.id = trace_id

    def update(self, **kwargs: object) -> None:
        if self._span is not None:
            with contextlib.suppress(Exception):
                self._span.update(**kwargs)  # type: ignore[union-attr]

    def score_trace(self, name: str, value: float) -> None:
        if self._span is not None:
            with contextlib.suppress(Exception):
                self._span.score_trace(name=name, value=value)  # type: ignore[union-attr]


@contextmanager
def sample_trace(
    client: object,
    sample_id: str,
    question: str,
    expected_output: str,
    question_type: str,
    config_name: str,
    run_id: str,
    project_name: str = "caiq-procurement-eval",
):  # type: ignore[return]
    """Create a Langfuse trace for a single CAIQ sample evaluation."""
    del project_name
    if client is None:
        yield None
        return

    with (
        client.start_as_current_observation(  # type: ignore[union-attr]
            name=f"caiq/{sample_id}",
            as_type="span",
            input={"question": question, "expected_output": expected_output},
            metadata={
                "run_id": run_id,
                "config": config_name,
                "question_type": question_type,
            },
        ) as span,
        propagate_attributes(session_id=run_id),
    ):
        trace_id = client.get_current_trace_id()  # type: ignore[union-attr]
        handle = _TraceHandle(span=span, trace_id=trace_id)
        try:
            yield handle
        finally:
            with contextlib.suppress(Exception):
                client.flush()  # type: ignore[union-attr]


def open_llm_span(
    trace: object,
    name: str,
    input_data: dict,
    model: str,
    metadata: Optional[dict] = None,
    parent_span_id: Optional[str] = None,
) -> object:
    del parent_span_id
    if trace is None:
        return None
    span = getattr(trace, "_span", None)
    if span is None:
        return None
    with contextlib.suppress(Exception):
        return span.start_observation(  # type: ignore[union-attr]
            name=name,
            as_type="generation",
            input=input_data,
            model=model,
            metadata=metadata or {},
        )
    return None


def close_span(
    span: object,
    output: Optional[dict] = None,
    usage: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    if span is None:
        return
    with contextlib.suppress(Exception):
        update_kwargs: dict = {}
        if output is not None:
            update_kwargs["output"] = output
        if usage:
            update_kwargs["usage_details"] = _normalize_usage(usage)
        if error:
            update_kwargs["level"] = "ERROR"
            update_kwargs["status_message"] = error
        if update_kwargs:
            span.update(**update_kwargs)  # type: ignore[union-attr]
        span.end()  # type: ignore[union-attr]


def log_trace_scores(trace: object, scores: dict) -> None:
    if trace is None:
        return
    for name, value in scores.items():
        if isinstance(value, (int, float)):
            with contextlib.suppress(Exception):
                if hasattr(trace, "score_trace"):
                    trace.score_trace(name=name, value=float(value))  # type: ignore[union-attr]
