"""Timing context manager."""

import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator


def iso_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TimingResult:
    """Result of a timing context manager."""

    start_ts: str = ""
    end_ts: str = ""
    elapsed_ms: float = 0.0


@contextmanager
def timed() -> Iterator[TimingResult]:
    """Context manager that measures wall-clock elapsed time in milliseconds."""
    result = TimingResult()
    result.start_ts = iso_now()
    t0 = time.time()
    yield result
    result.elapsed_ms = (time.time() - t0) * 1000.0
    result.end_ts = iso_now()
