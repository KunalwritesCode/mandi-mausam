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


_QTY_RE = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*(?:quintals?|qtl|क्विंटल|क्विण्टल)", re.I)

_ASK_ALL = {
    "en": "Please tell me your crop, your village or town, and how many quintals you have to sell.",
    "hi": "कृपया बताइए: आपकी फसल कौन सी है, आप किस गाँव या शहर में हैं, और कितने क्विंटल बेचना है?",
    "mr": "कृपया सांगा: तुमचे पीक कोणते आहे, तुम्ही कोणत्या गावात किंवा शहरात आहात, आणि किती क्विंटल विकायचे आहे?",
}
_ASK_QTY = {
    "en": "How many quintals do you have to sell? Please give a number above zero.",
    "hi": "आपके पास कितने क्विंटल है? कृपया शून्य से ज़्यादा संख्या बताइए।",
    "mr": "तुमच्याकडे किती क्विंटल आहे? कृपया शून्यापेक्षा जास्त संख्या सांगा.",
}


def precheck(question: str, quantity: float | None, language: str = "en") -> str | None:
    """A friendly question to ask back when the input cannot be answered yet; None if it can proceed.

    Cheap, instant and deterministic, so the AI model is never asked to guess a crop, place or quantity.
    """
    words = re.findall(r"[\w\u0900-\u097F]+", question)
    if len(words) < 3:
        return _ASK_ALL.get(language, _ASK_ALL["en"])
    if quantity is not None and quantity <= 0:
        return _ASK_QTY.get(language, _ASK_QTY["en"])
    for m in _QTY_RE.finditer(question.translate(_DEVANAGARI)):
        try:
            if float(m.group(1)) <= 0:
                return _ASK_QTY.get(language, _ASK_QTY["en"])
        except ValueError:
            continue
    return None


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


# Fixed public numbers the agent is told to quote: Kisan Call Centre toll-free 1800-180-1551.
ALWAYS_ALLOWED = {1800.0, 180.0, 1551.0}


def allowed_numbers(tool_results: list[Any], user_inputs: dict[str, Any]) -> set[float]:
    allowed: set[float] = set(range(0, 32)) | ALWAYS_ALLOWED  # small counts, day numbers, helpline
    for r in tool_results:
        _collect_numbers(r, allowed)
    _collect_numbers(user_inputs, allowed)
    # Figures the model may legitimately state: the farmer's quantity times a per-quintal figure from the data
    # (a total), and large totals written in lakh or crore. Invented numbers still fail.
    qtys = {v for v in numbers_in(str(user_inputs.get("q", ""))) if 0 < v <= 100000}
    if user_inputs.get("qty"):
        qtys.add(float(user_inputs["qty"]))
    per_unit = [a for a in allowed if 100 <= a <= 200000]
    for q in qtys:
        for a in per_unit:
            allowed.add(round(q * a, 2))
            allowed.add(float(round(q * a)))
    for a in list(allowed):
        if a >= 100000:
            allowed.add(round(a / 100000, 2))
            allowed.add(round(a / 10000000, 2))
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
