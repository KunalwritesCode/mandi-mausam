"""Guardrails around the LLM.

1. Input checks: length, empty input, control characters.
2. Grounding check: every number the LLM writes must appear in a tool result
   (prices, distances, dates, percentages). Unsupported numbers trigger one
   self-correction round; if they persist, the answer is flagged.
"""

from __future__ import annotations

import json
import re
from typing import Any

MAX_QUESTION_CHARS = 600

# Western digits plus Devanagari digits (Hindi/Marathi answers may use either).
_DEVANAGARI = str.maketrans("०१२३४५६७८९", "0123456789")
_NUM_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)(?![\w])")


def clean_question(text: str) -> tuple[str | None, str | None]:
    """Return (clean_text, error)."""
    if text is None:
        return None, "Please type or say your question."
    t = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", str(text)).strip()
    if not t:
        return None, "Please type or say your question."
    if len(t) > MAX_QUESTION_CHARS:
        return None, f"Please keep the question under {MAX_QUESTION_CHARS} characters."
    return t, None


def numbers_in(text: str) -> set[float]:
    found = set()
    for m in _NUM_RE.finditer(text.translate(_DEVANAGARI)):
        try:
            found.add(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return found


def _collect_numbers(obj: Any, out: set[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
        out.add(float(round(obj)))
    elif isinstance(obj, str):
        out.update(numbers_in(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, out)


def allowed_numbers(tool_results: list[Any], user_inputs: dict[str, Any]) -> set[float]:
    allowed: set[float] = set(range(0, 32))  # small counts, day numbers, list ordinals
    for r in tool_results:
        _collect_numbers(r, allowed)
    _collect_numbers(user_inputs, allowed)
    # Dates like 2026-11-01 appear in text as 2026, 11, 1, and as 1 Nov etc.
    return allowed


def unsupported_numbers(answer: str, allowed: set[float]) -> list[float]:
    bad = []
    for n in numbers_in(answer):
        if n in allowed:
            continue
        # Allow rounding to the nearest 10 or 100 of a real value (e.g. "about 3,900").
        if any(abs(n - a) <= max(1.0, 0.005 * abs(a)) for a in allowed if a > 31):
            continue
        bad.append(n)
    return sorted(bad)


def compact(obj: Any, limit: int = 6000) -> str:
    """JSON for the LLM, trimmed to keep prompts small."""
    s = json.dumps(obj, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + "...(truncated)"
