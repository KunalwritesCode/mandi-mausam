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
from app.agent.prompts import LANGUAGES, system_prompt
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
    """Extra request fields: the reasoning level and the token budget."""
    effort = (settings.llm_reasoning_effort or "").strip().lower()
    out: dict[str, Any] = {"max_tokens": settings.llm_max_tokens}
    if effort in ("none", "off", "null", "disabled"):
        out["extra_body"] = {"reasoning_effort": None}   # sent as JSON null: thinking switched off
    elif effort:
        out["reasoning_effort"] = effort
    return out


def _llm_error_detail(exc: Exception) -> str:
    """A short, secret-free description of why the model call failed."""
    if isinstance(exc, APITimeoutError):
        return f"AI model timed out after {settings.llm_timeout_s:.0f}s (model: {settings.llm_model})"
    if isinstance(exc, APIStatusError):
        return f"AI model rejected the request: HTTP {exc.status_code}: {str(exc)[:200]}"
    return f"AI model error: {exc.__class__.__name__}: {str(exc)[:200]}"


_THINK_RE = re.compile(r"<think>.*?(</think>|$)", re.S | re.I)


def _salvage(text: str) -> dict[str, Any] | None:
    """Last resort for a reply cut off mid-JSON: recover the recommendation and the answer text."""
    rec = re.search(r'"recommendation"\s*:\s*"([A-Z_]+)"', text)
    ans = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)', text, re.S)
    if not (rec and ans and ans.group(1).strip()):
        return None
    raw = ans.group(1)
    try:
        answer = json.loads('"' + raw + '"', strict=False)
    except json.JSONDecodeError:
        answer = raw
    return {"recommendation": rec.group(1), "best_mandi": None, "answer": answer.strip(), "reasons": [], "ask_farmer": None}


def _parse_json(text: str) -> dict[str, Any] | None:
    """Pull the JSON object out of a model reply.

    Tolerates <think> blocks, ``` fences, text before or after the object, raw newlines inside strings,
    and (as a last resort) a reply cut off before the closing brace.
    """
    if not text:
        return None
    text = _THINK_RE.sub("", text)
    dec = json.JSONDecoder(strict=False)
    pos = text.find("{")
    while pos != -1:
        try:
            obj, _ = dec.raw_decode(text[pos:])
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and ("answer" in obj or "recommendation" in obj):
            return obj
        pos = text.find("{", pos + 1)
    return _salvage(text)


def _llm_view(name: str, result: dict[str, Any]) -> dict[str, Any]:
    """A lean copy of a tool result for the model: fewer tokens, faster, same facts."""
    if not isinstance(result, dict):
        return result
    if name == "find_place":
        return {k: result[k] for k in ("found", "name", "district", "state", "lat", "lon", "error") if k in result}
    if name == "get_weather_outlook":
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error")}
        keep = ("date", "rain_mm", "rain_chance_pct", "humidity_mean_pct", "risk")
        return {"ok": True, "summary": result.get("summary"), "days": [{k: d.get(k) for k in keep} for d in result.get("days", [])]}
    if name == "compare_mandis":
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error")}
        keep = ("rank", "market", "district", "arrival_date", "age_days", "stale", "modal_price", "distance_km",
                "drive_minutes", "transport_per_quintal_rs", "net_price_per_quintal_rs", "net_total_rs")
        return {
            "ok": True,
            **{k: result.get(k) for k in ("commodity", "state", "distance_method", "quantity_quintals",
                                           "transport_rate_per_km", "transport_cost_known", "coverage_note")},
            "mandis": [{k: m.get(k) for k in keep} for m in result.get("mandis", [])],
            "mandis_not_located_count": len(result.get("mandis_not_located") or []),
        }
    return result


FORMAT_REMINDER = (
    "Now give your final answer as ONE JSON object only, with no other text. Keys: "
    '"recommendation" (SELL_NOW, HOLD, NEED_INFO or CANNOT_HELP), "best_mandi" (a market name from the tool data, or null), '
    '"answer" (3-5 short spoken-style sentences in {language}), "reasons" (list of short strings, each with a number '
    'from the tool data), "ask_farmer" (one question, or null). Use only numbers from the tool results or my message.'
)


def _finalize(client: OpenAI, messages: list[dict[str, Any]], language: str) -> dict[str, Any] | None:
    """Re-ask for the final JSON (JSON mode first, then plain) when the first reply was unusable."""
    reminder = {"role": "user", "content": FORMAT_REMINDER.replace("{language}", LANGUAGES.get(language, "English"))}
    for kwargs in ({"response_format": {"type": "json_object"}}, {}):
        try:
            resp = client.chat.completions.create(
                model=settings.llm_model,
                messages=[*messages, reminder],
                tools=TOOL_SCHEMAS,
                tool_choice="none",
                temperature=0,
                **kwargs,
                **_extra(),
            )
        except OpenAIError:
            continue
        parsed = _parse_json(resp.choices[0].message.content or "")
        if parsed:
            return parsed
    return None


def _fallback_answer(tr: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """A plain answer built directly from tool data, used only if the model gives nothing usable."""
    m = tr.get("compare_mandis") or {}
    rows = m.get("mandis") or []
    if not m.get("ok") or not rows:
        return None
    fresh = [r for r in rows if not r.get("stale")] or rows
    best = fresh[0]
    s = (tr.get("get_weather_outlook") or {}).get("summary") or {}
    name = str(best.get("market", "")).strip()
    parts = [f"The highest reported price is {best.get('modal_price'):.0f} rupees per quintal at {name}"
             + (f", {best['distance_km']} km away" if best.get("distance_km") is not None else "")
             + (f" (reported {best['arrival_date']})." if best.get("arrival_date") else ".")]
    has_net = best.get("net_price_per_quintal_rs") is not None
    if has_net:
        parts.append(f"After transport you would get about {best['net_price_per_quintal_rs']} rupees per quintal.")
    if s:
        parts.append(f"The next 7 days have {s.get('rainy_days')} rainy and {s.get('humid_days')} humid days, "
                     f"so the storage risk is {s.get('storage_risk')}.")
    if m.get("coverage_note"):
        parts.append(m["coverage_note"])
    risky = s.get("storage_risk") in ("medium", "high")
    return {
        "recommendation": "SELL_NOW" if (risky and has_net) else "NEED_INFO",
        "best_mandi": name or None,
        "answer": " ".join(parts),
        "reasons": [f"Price {best.get('modal_price'):.0f} rupees per quintal at {name}"],
        "ask_farmer": None if has_net else "Tell me your quantity and your transport cost per km so I can work out the price after transport.",
    }


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


class _LiveTrace(list):
    """A trace that tells a listener about each step the moment it is recorded (for live progress)."""

    def __init__(self, on_step: Callable[[dict[str, Any]], None]) -> None:
        super().__init__()
        self._on_step = on_step

    def append(self, item: dict[str, Any]) -> None:  # type: ignore[override]
        super().append(item)
        try:
            self._on_step(dict(item))
        except Exception:  # noqa: BLE001 - a broken listener must never break an answer
            pass


def run_agent(
    question: str,
    language: str = "en",
    quantity_quintals: float | None = None,
    transport_rate_per_km: float | None = None,
    on_step: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run the full plan -> tools -> answer -> check loop. `on_step` is called with each trace step as it happens."""
    started = time.time()
    trace: list[dict[str, Any]] = _LiveTrace(on_step) if on_step else []
    tool_results: dict[str, dict[str, Any]] = {}

    q, err = guardrails.clean_question(question)
    if err:
        return {"ok": False, "error": err, "trace": trace}
    ask = guardrails.precheck(q, quantity_quintals, language)
    if ask:
        trace.append({"step": "precheck", "ok": True, "detail": "Not enough information yet, so asked the farmer instead of guessing"})
        return {"ok": True, "recommendation": "NEED_INFO", "best_mandi": None, "answer": ask, "reasons": [],
                "ask_farmer": ask, "grounded": True, "unsupported_numbers": [], "place": None, "weather": None,
                "mandis": None, "trace": trace, "elapsed_s": 0.0, "model": settings.llm_model}
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
    last_finish = None

    for step in range(settings.llm_max_steps):
        t_llm = time.time()
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
        last_finish = getattr(resp.choices[0], "finish_reason", None)
        wanted = [c.function.name for c in (msg.tool_calls or [])]
        trace.append({
            "step": "llm_call", "ok": last_finish != "length", "ms": round((time.time() - t_llm) * 1000),
            "detail": (f"decided to call {', '.join(wanted)}" if wanted else "wrote the answer")
                      + (" (cut off: hit the token limit)" if last_finish == "length" else ""),
        })
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
                {"role": "tool", "tool_call_id": call.id, "content": guardrails.compact(_llm_view(name, result))}
            )
    else:
        trace.append({"step": "limit", "ok": False, "detail": "Step limit reached"})

    parsed = _parse_json(final_text)
    if not parsed:
        shown = re.sub(r"\s+", " ", _THINK_RE.sub("", final_text)).strip()[:140]
        trace.append({"step": "format", "ok": False,
                      "detail": f"First model reply was not usable JSON (finish_reason={last_finish}; reply={shown!r}); asking again"})
        parsed = _finalize(client, messages, language)
        if parsed:
            trace.append({"step": "format", "ok": True, "detail": "Second attempt returned a clean answer"})
    if not parsed:
        parsed = _fallback_answer(tool_results)
        if parsed:
            trace.append({"step": "format", "ok": True, "detail": "Model gave no usable answer; showing a plain summary built directly from the live data"})
    if not parsed:
        parsed = {"recommendation": "CANNOT_HELP", "best_mandi": None, "reasons": [],
                  "answer": re.sub(r"\s+", " ", _THINK_RE.sub("", final_text)).strip()[:800]
                  or "Sorry, I could not prepare an answer. Please try again."}

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
