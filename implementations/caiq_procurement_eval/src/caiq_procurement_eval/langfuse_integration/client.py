"""Langfuse client singleton with graceful degradation.

Returns None when LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not set,
so every caller can guard with ``if client:``.
"""

import logging
import os
from contextlib import suppress

from dotenv import load_dotenv
from langfuse import Langfuse


logging.getLogger("opentelemetry.attributes").setLevel(logging.ERROR)

try:
    from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
    _google_instrumentor = GoogleGenAIInstrumentor()
except Exception:
    _google_instrumentor = None  # type: ignore[assignment]

try:
    from openinference.instrumentation.openai import OpenAIInstrumentor
    _openai_instrumentor = OpenAIInstrumentor()
except Exception:
    _openai_instrumentor = None  # type: ignore[assignment]


_client = None
_initialised = False


def get_client():
    """Initialize and return a globally cached Langfuse client.

    Returns
    -------
    Langfuse or None
    """
    global _client, _initialised  # noqa: PLW0603
    if _initialised:
        return _client

    _initialised = True

    with suppress(Exception):
        load_dotenv()

    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")

    if not public_key or not secret_key:
        return None

    try:
        kwargs: dict = {"public_key": public_key, "secret_key": secret_key}
        host = os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_BASE_URL", "")
        if host:
            kwargs["host"] = host

        _client = Langfuse(**kwargs)

        if _google_instrumentor is not None:
            with suppress(Exception):
                _google_instrumentor.instrument()
        if _openai_instrumentor is not None:
            with suppress(Exception):
                _openai_instrumentor.instrument()
    except Exception as exc:
        print(f"[langfuse] client init failed: {exc}")
        _client = None

    return _client


def reset_client() -> None:
    """Clear the cached client and reset initialization state."""
    global _client, _initialised  # noqa: PLW0603
    _client = None
    _initialised = False
