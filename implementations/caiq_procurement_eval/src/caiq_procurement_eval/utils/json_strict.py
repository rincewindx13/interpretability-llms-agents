"""Strict JSON parsing policy with repair fallback."""

import json
import re
from typing import Any, Optional

from json_repair import repair_json


def parse_strict(
    text: str,
    required_keys: Optional[list[str]] = None,
) -> tuple[dict[str, Any], bool]:
    """Parse JSON from a string with automatic cleanup and repair fallback."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        result = json.loads(text)
        if _check_keys(result, required_keys):
            return result, True
        raise ValueError("Missing required keys")
    except (json.JSONDecodeError, ValueError):
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if _check_keys(result, required_keys):
                return result, True
        except (json.JSONDecodeError, ValueError):
            pass

    try:
        repaired = repair_json(text)
        result = json.loads(repaired)
        if _check_keys(result, required_keys):
            return result, False
    except Exception:
        pass

    return {}, False


def _check_keys(result: Any, required_keys: Optional[list[str]]) -> bool:
    if not isinstance(result, dict):
        return False
    return not required_keys or all(k in result for k in required_keys)
