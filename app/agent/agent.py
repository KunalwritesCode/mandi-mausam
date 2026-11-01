"""The decision agent: an LLM that plans and calls tools, with a step limit,
error feedback for self-correction, and a grounding check on the final answer.

Every step is recorded in `trace` so the UI can show judges how it decided.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from openai import APIStatusError, APITimeoutError, OpenAI, OpenAIError

from app.agent import guardrails
from app.agent.prompts import system_prompt
from app.config import settings
from app.tools import geo, mandi, weather

# ---------------------------------------------------------------- tool registry

TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "find_place": geo.find_place,
    "get_weather_outlook": weather.get_weather_outlook,
    "compare_mandis": mandi.compare_mandis,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "find_place",
            "description": "Find a village or town in India. Returns its district, state, latitude and longitude.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Village or town name, in English letters."},
                    "state": {"type": "string", "description": "Indian state, if known, e.g. Maharashtra."},
                    "district": {"type": "string", "description": "District, if known, e.g. Nashik."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_outlook",
            "description": "7-day rain and humidity forecast with storage and transport risk for stored crop.",
            "parameters": {
                "type": "object",
                "properties": {"lat": {"type": "number"}, "lon": {"type": "number"}},
                "required": ["lat", "lon"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_mandis",
            "description": (
                "Latest official mandi prices (data.gov.in Agmarknet) for a crop at the nearest mandis, "
                "with road distance and, if quantity and transport rate are given, price after transport."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "commodity": {"type": "string", "description": "Agmarknet English name, e.g. Onion."},
                    "state": {"type": "string", "description": "State name as returned by find_place."},
                    "origin_lat": {"type": "number"},
                    "origin_lon": {"type": "number"},
                    "quantity_quintals": {"type": "number", "description": "Only if the farmer said it."},
                    "transport_rate_per_km": {"type": "number", "description": "Rupees per km, only if the farmer said it."},
                },
                "required": ["commodity", "state", "origin_lat", "origin_lon"],
            },
        },
    },
]

RECOMMENDATIONS = {"SELL_NOW", "HOLD", "NEED_INFO", "CANNOT_HELP"}


def _client() -> OpenAI:
    # No hidden SDK retries: a hung model should fail fast and visibly.
    return OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url, timeout=settings.llm_timeout_s, max_retries=0)


def _extra() -> dict[str, Any]:
    return {"reasoning_effort": settings.llm_reasoning_effort} if settings.llm_reasoning_effort else {}


def _llm_error_detail(exc: Exception) -> str:
    """A short, secret-free description of why the model call failed."""
    if isinstance(exc, APITimeoutError):
        return f"AI model timed out after {settings.llm_timeout_s:.0f}s (model: {settings.llm_model})"
    if isinstance(exc, APIStatusError):
        return f"AI model rejected the request: HTTP {exc.status_code}: {str(exc)[:200]}"
    return f"AI model error: {exc.__class__.__name__}: {str(exc)[:200]}"


def _parse_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _summarise_tool(name: str, result: dict[str, Any]) -> str:
    if not result.get("ok", result.get("found", True)):
        return f"failed: {result.get('error', 'unknown error')}"
    if name == "find_place":
        return f"{result.get('name')}, {result.get('district')}, {result.get('state')}"
    if name == "get_weather_outlook":
        s = result.get("summary", {})
        return f"{s.get('rainy_days')} rainy and {s.get('humid_days')} humid days in 7; storage risk {s.get('storage_risk')}"
    if name == "compare_mandis":
        ms = result.get("mandis", [])
        return f"{len(ms)} mandis compared ({result.get('distance_method')} distance)"
    return "done"


def run_agent(
    question: str,
    language: str = "en",
    quantity_quintals: float | None = None,
    transport_rate_per_km: float | None = None,
) -> dict[str, Any]:
    """Run the full plan -> tools -> answer -> check loop."""
    started = time.time()
    trace: list[dict[str, Any]] = []
    tool_results: dict[str, dict[str, Any]] = {}

    q, err = guardrails.clean_question(question)
    if err:
        return {"ok": False, "error": err, "trace": trace}
    if not settings.llm_api_key:
        return {"ok": False, "error": "No AI model key is set on the server (LLM_API_KEY or GEMINI_API_KEY).", "trace": trace}

    extras = []
    if quantity_quintals is not None:
        extras.append(f"Quantity: {quantity_quintals} quintals.")
    if transport_rate_per_km is not None:
        extras.append(f"Transport cost: Rs {transport_rate_per_km} per km.")
    user_msg = q + (("\n" + " ".join(extras)) if extras else "")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt(language)},
        {"role": "user", "content": user_msg},
    ]
    client = _client()
    final_text = ""

    for step in range(settings.llm_max_steps):
        try:
            resp = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.2,
                **_extra(),
            )
        except OpenAIError as exc:
            trace.append({"step": "llm", "ok": False, "detail": _llm_error_detail(exc)})
            return {"ok": False, "error": "The AI model is not responding. Please try again.", "trace": trace}

        msg = resp.choices[0].message
        # Keep only the standard assistant fields. tool_calls are kept exactly as returned,
        # because Gemini 3 stores its thought signatures inside them. Provider-specific extras
        # (e.g. reasoning_content) are dropped so any OpenAI-compatible server accepts the history.
        raw = msg.model_dump(exclude_none=True)
        turn: dict[str, Any] = {"role": "assistant"}
        if raw.get("content"):
            turn["content"] = raw["content"]
        if raw.get("tool_calls"):
            turn["tool_calls"] = raw["tool_calls"]
        if "content" not in turn and "tool_calls" not in turn:
            turn["content"] = ""
        messages.append(turn)

        if not msg.tool_calls:
            final_text = msg.content or ""
            break

        for call in msg.tool_calls:
            name = call.function.name
            t0 = time.time()
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            # Quantity and rate come from the farmer only, never from the model's imagination.
            if name == "compare_mandis":
                args["quantity_quintals"] = quantity_quintals if quantity_quintals is not None else args.get("quantity_quintals")
                args["transport_rate_per_km"] = (
                    transport_rate_per_km if transport_rate_per_km is not None else args.get("transport_rate_per_km")
                )
                if not _mentioned(q, args.get("quantity_quintals")) and quantity_quintals is None:
                    args["quantity_quintals"] = None
                if not _mentioned(q, args.get("transport_rate_per_km")) and transport_rate_per_km is None:
                    args["transport_rate_per_km"] = None
            fn = TOOLS.get(name)
            if fn is None:
                result = {"ok": False, "error": f"Unknown tool {name}"}
            else:
                try:
                    result = fn(**args)
                except TypeError as exc:
                    result = {"ok": False, "error": f"Bad arguments: {exc}"}
                except Exception as exc:  # noqa: BLE001 - surface any tool failure to the model
                    result = {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}
            tool_results[name] = result
            ok = bool(result.get("ok", result.get("found", True)))
            trace.append(
                {
                    "step": name,
                    "args": {k: v for k, v in args.items() if v is not None},
                    "ok": ok,
                    "ms": round((time.time() - t0) * 1000),
                    "detail": _summarise_tool(name, result),
                }
            )
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": guardrails.compact(result)}
            )
    else:
        trace.append({"step": "limit", "ok": False, "detail": "Step limit reached"})

    parsed = _parse_json(final_text)
    if not parsed:
        trace.append({"step": "format", "ok": False, "detail": "Model answer was not valid JSON"})
        parsed = {"recommendation": "CANNOT_HELP", "answer": final_text.strip()[:800], "reasons": [], "best_mandi": None}

    # ---- grounding check, with one self-correction round
    allowed = guardrails.allowed_numbers(
        list(tool_results.values()), {"q": q, "qty": quantity_quintals, "rate": transport_rate_per_km}
    )
    answer_text = " ".join([parsed.get("answer") or ""] + list(parsed.get("reasons") or []))
    bad = guardrails.unsupported_numbers(answer_text, allowed)
    grounded = not bad
    if bad:
        trace.append({"step": "grounding_check", "ok": False, "detail": f"Unsupported numbers {bad}; asking model to fix"})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"These numbers are not in any tool result: {bad}. Rewrite the same JSON using only numbers "
                    "from the tool results or my message. Remove any number you cannot support."
                ),
            }
        )
        try:
            resp = client.chat.completions.create(model=settings.llm_model, messages=messages, temperature=0, **_extra())
            fixed = _parse_json(resp.choices[0].message.content or "")
        except OpenAIError:
            fixed = None
        if fixed:
            parsed = fixed
            answer_text = " ".join([parsed.get("answer") or ""] + list(parsed.get("reasons") or []))
            bad = guardrails.unsupported_numbers(answer_text, allowed)
            grounded = not bad
        trace.append({"step": "grounding_check", "ok": grounded, "detail": "All numbers traced to tool data" if grounded else f"Still unsupported: {bad}"})
    else:
        trace.append({"step": "grounding_check", "ok": True, "detail": "All numbers traced to tool data"})

    rec = parsed.get("recommendation")
    if rec not in RECOMMENDATIONS:
        rec = "NEED_INFO"

    return {
        "ok": True,
        "recommendation": rec,
        "best_mandi": parsed.get("best_mandi"),
        "answer": parsed.get("answer") or "",
        "reasons": parsed.get("reasons") or [],
        "ask_farmer": parsed.get("ask_farmer"),
        "grounded": grounded,
        "unsupported_numbers": bad,
        "place": tool_results.get("find_place"),
        "weather": tool_results.get("get_weather_outlook"),
        "mandis": tool_results.get("compare_mandis"),
        "trace": trace,
        "elapsed_s": round(time.time() - started, 1),
        "model": settings.llm_model,
    }


def _mentioned(text: str, value: Any) -> bool:
    """True if a numeric value the model passed actually appears in the farmer's text."""
    if value is None:
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return v in guardrails.numbers_in(text)
