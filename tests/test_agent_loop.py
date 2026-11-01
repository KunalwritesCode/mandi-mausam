"""Agent-loop mechanics with a scripted stand-in LLM and stand-in tools.

This checks plumbing only (tool dispatch, argument guards, grounding self-correction).
The real app always calls the live LLM and live APIs.
"""

import json
from types import SimpleNamespace as NS

import pytest

from app.agent import agent as A


def _tool_call(i, name, args):
    return NS(id=f"call_{i}", type="function", function=NS(name=name, arguments=json.dumps(args)))


class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content, self.tool_calls = content, tool_calls

    def model_dump(self, exclude_none=True):
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [{"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}} for c in self.tool_calls]
        return {k: v for k, v in d.items() if v is not None}


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return NS(choices=[NS(message=self.script.pop(0))])


@pytest.fixture
def fake_tools(monkeypatch):
    seen = {}

    def find_place(query, state=None, district=None):
        return {"found": True, "name": "Lasalgaon", "district": "Nashik", "state": "Maharashtra", "lat": 20.15, "lon": 74.23}

    def weather(lat, lon, days=7):
        return {"ok": True, "summary": {"rainy_days": 2, "humid_days": 6, "storage_risk": "high"}, "days": []}

    def compare(**kw):
        seen["compare"] = kw
        return {"ok": True, "mandis": [{"market": "Lasalgaon", "modal_price": 3900, "distance_km": 4.2}], "distance_method": "road"}

    monkeypatch.setattr(A, "TOOLS", {"find_place": find_place, "get_weather_outlook": weather, "compare_mandis": compare})
    monkeypatch.setattr(A.settings.__class__, "llm_api_key", property(lambda self: "test"), raising=False)
    return seen


def _final(answer):
    return _Msg(content=json.dumps({"recommendation": "SELL_NOW", "best_mandi": "Lasalgaon", "answer": answer, "reasons": [], "ask_farmer": None}))


def test_full_loop_and_quantity_guard(monkeypatch, fake_tools):
    script = [
        _Msg(tool_calls=[_tool_call(1, "find_place", {"query": "Lasalgaon"})]),
        _Msg(tool_calls=[_tool_call(2, "get_weather_outlook", {"lat": 20.15, "lon": 74.23}),
                         # model tries to invent a transport rate the farmer never gave
                         _tool_call(3, "compare_mandis", {"commodity": "Onion", "state": "Maharashtra", "origin_lat": 20.15,
                                                          "origin_lon": 74.23, "quantity_quintals": 20, "transport_rate_per_km": 35})]),
        _final("Sell today at Lasalgaon for 3,900 rupees per quintal; it is 4.2 km away and 6 humid days are ahead."),
    ]
    fake = FakeClient(script)
    monkeypatch.setattr(A, "_client", lambda: fake)
    out = A.run_agent("I have 20 quintals of onion near Lasalgaon. Sell now?", "en")
    assert out["ok"] and out["recommendation"] == "SELL_NOW" and out["grounded"]
    assert fake_tools["compare"]["quantity_quintals"] == 20          # stated by farmer: kept
    assert fake_tools["compare"]["transport_rate_per_km"] is None    # invented by model: dropped
    tool_steps = [t["step"] for t in out["trace"] if t["step"] in ("find_place", "get_weather_outlook", "compare_mandis")]
    assert tool_steps == ["find_place", "get_weather_outlook", "compare_mandis"]
    assert any(t["step"] == "llm_call" and "find_place" in t["detail"] for t in out["trace"])


def test_grounding_self_correction(monkeypatch, fake_tools):
    script = [
        _Msg(tool_calls=[_tool_call(1, "find_place", {"query": "Lasalgaon"})]),
        _Msg(tool_calls=[_tool_call(2, "compare_mandis", {"commodity": "Onion", "state": "Maharashtra",
                                                          "origin_lat": 20.15, "origin_lon": 74.23})]),
        _final("Prices may rise to 5,200 next week."),           # invented number
        _final("Sell today at Lasalgaon for 3,900 per quintal."),  # corrected
    ]
    monkeypatch.setattr(A, "_client", lambda: FakeClient(script))
    out = A.run_agent("Onion near Lasalgaon, sell?", "en")
    assert out["grounded"] and "3,900" in out["answer"]
    assert any(t["step"] == "grounding_check" and not t["ok"] for t in out["trace"])


def test_empty_final_reply_is_reasked(monkeypatch, fake_tools):
    script = [
        _Msg(tool_calls=[_tool_call(1, "find_place", {"query": "Lasalgaon"})]),
        _Msg(tool_calls=[_tool_call(2, "compare_mandis", {"commodity": "Onion", "state": "Maharashtra",
                                                          "origin_lat": 20.15, "origin_lon": 74.23})]),
        _Msg(content=""),                                                        # model returns nothing
        _final("Sell today at Lasalgaon for 3,900 per quintal, it is 4.2 km away."),  # re-ask works
    ]
    monkeypatch.setattr(A, "_client", lambda: FakeClient(script))
    out = A.run_agent("Onion near Lasalgaon, sell?", "en")
    assert out["ok"] and out["grounded"] and "Lasalgaon" in out["answer"]
    assert any(t["step"] == "format" and t["ok"] for t in out["trace"])


def test_plain_summary_when_model_gives_nothing(monkeypatch, fake_tools):
    script = [
        _Msg(tool_calls=[_tool_call(1, "find_place", {"query": "Lasalgaon"})]),
        _Msg(tool_calls=[_tool_call(2, "compare_mandis", {"commodity": "Onion", "state": "Maharashtra",
                                                          "origin_lat": 20.15, "origin_lon": 74.23})]),
        _Msg(content=""), _Msg(content=""), _Msg(content=""),
    ]
    monkeypatch.setattr(A, "_client", lambda: FakeClient(script))
    out = A.run_agent("Onion near Lasalgaon, sell?", "en")
    assert out["ok"] and "3900" in out["answer"] and out["grounded"]
    assert out["recommendation"] in {"NEED_INFO", "SELL_NOW"}


def test_parse_json_handles_think_blocks_and_fences():
    raw = '<think>hmm {not json}</think>\n```json\n{"recommendation": "HOLD", "answer": "ok"}\n```'
    assert A._parse_json(raw) == {"recommendation": "HOLD", "answer": "ok"}


def test_parse_json_is_tolerant():
    raw_newline = '{"recommendation": "SELL_NOW", "answer": "line one\nline two"}'
    assert A._parse_json(raw_newline)["answer"] == "line one\nline two"
    assert A._parse_json('Sure! {"recommendation": "HOLD", "answer": "ok"} Hope that helps {x}')["recommendation"] == "HOLD"
    cut = '{"recommendation": "CANNOT_HELP", "best_mandi": null, "answer": "I cannot share that. I can help you compare mandi prices and'
    out = A._parse_json(cut)
    assert out["recommendation"] == "CANNOT_HELP" and out["answer"].startswith("I cannot share that")
    assert A._parse_json("no json here") is None and A._parse_json("") is None


def test_reasoning_switch(monkeypatch):
    import dataclasses
    for effort, expect in (("none", {"extra_body": {"reasoning_effort": None}}), ("low", {"reasoning_effort": "low"}), ("", {})):
        monkeypatch.setattr(A, "settings", dataclasses.replace(A.settings, llm_reasoning_effort=effort, llm_max_tokens=1500))
        got = A._extra()
        assert got.pop("max_tokens") == 1500 and got == expect


def test_missing_inputs_never_reach_the_model(monkeypatch):
    def boom():
        raise AssertionError("the model must not be called")
    monkeypatch.setattr(A, "_client", boom)
    for q in ("sell?", "Onion near Lasalgaon, 0 quintals. Sell?"):
        out = A.run_agent(q, "en")
        assert out["ok"] and out["recommendation"] == "NEED_INFO" and out["ask_farmer"]
    assert "क्विंटल" in A.run_agent("बेचूँ?", "hi")["answer"]


def test_live_steps_are_reported_as_they_happen(monkeypatch, fake_tools):
    script = [
        _Msg(tool_calls=[_tool_call(1, "find_place", {"query": "Lasalgaon"})]),
        _Msg(tool_calls=[_tool_call(2, "compare_mandis", {"commodity": "Onion", "state": "Maharashtra",
                                                          "origin_lat": 20.15, "origin_lon": 74.23})]),
        _final("Sell today at Lasalgaon for 3,900 per quintal."),
    ]
    monkeypatch.setattr(A, "_client", lambda: FakeClient(script))
    seen = []
    out = A.run_agent("Onion near Lasalgaon, sell?", "en", on_step=seen.append)
    assert [s["step"] for s in seen] == [s["step"] for s in out["trace"]]
    assert {"find_place", "compare_mandis", "llm_call", "grounding_check"} <= {s["step"] for s in seen}
    # a listener that crashes must not break the answer
    monkeypatch.setattr(A, "_client", lambda: FakeClient([_Msg(tool_calls=[_tool_call(1, "find_place", {"query": "Lasalgaon"})]), _final("Sell today at Lasalgaon.")]))
    assert A.run_agent("Onion near Lasalgaon, sell?", "en", on_step=lambda s: 1 / 0)["ok"]
