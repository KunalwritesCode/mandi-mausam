"""FastAPI app: JSON API for the agent and voice, plus the static web page."""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import voice
from app.agent.agent import run_agent
from app.config import settings
from app.tools import mandi, weather

STATIC = Path(__file__).resolve().parent.parent / "static"
MAX_AUDIO_BYTES = 2_000_000  # about 30 s of compressed speech

app = FastAPI(title="Mandi-Mausam Agent", version="0.1.0")


class AskRequest(BaseModel):
    question: str = Field(..., max_length=600)
    language: Literal["en", "hi", "mr"] = "en"
    quantity_quintals: float | None = Field(None, gt=0, le=10000)
    transport_rate_per_km: float | None = Field(None, ge=0, le=1000)


class SpeakRequest(BaseModel):
    text: str = Field(..., max_length=2000)
    language: Literal["en", "hi", "mr"] = "en"


@app.get("/api/health")
def health() -> dict:
    """Liveness plus one real upstream call, so a judge can see the data path is live."""
    w = weather.get_weather_outlook(20.15, 74.23, days=1)  # Lasalgaon, Nashik
    mp = mandi.ping()
    return {
        "status": "ok",
        "weather_api": "ok" if w.get("ok") else f"down: {w.get('error')}",
        "weather_source": (w.get("source") or {}).get("name"),
        "weather_fetched_at": (w.get("source") or {}).get("fetched_at"),
        "mandi_api": "ok" if mp.get("ok") else f"down: {mp.get('error')}",
        "mandi_fetched_at": mp.get("fetched_at"),
        "configured": {
            "llm": bool(settings.llm_api_key),
            "mandi_prices": bool(settings.data_gov_api_key),
            "voice": bool(settings.sarvam_api_key),
        },
        "model": settings.llm_model,
    }


HERO_PLACE = {"name": "Lasalgaon", "district": "Nashik", "lat": 20.15, "lon": 74.23}


@app.get("/api/sky")
def sky() -> dict:
    """Current conditions at Lasalgaon for the home-page sky. Real data or an explicit error, never a guess."""
    return {"place": HERO_PLACE, **weather.get_current_sky(HERO_PLACE["lat"], HERO_PLACE["lon"])}


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    return run_agent(
        req.question,
        language=req.language,
        quantity_quintals=req.quantity_quintals,
        transport_rate_per_km=req.transport_rate_per_km,
    )


@app.post("/api/ask_stream")
def ask_stream(req: AskRequest) -> StreamingResponse:
    """Same as /api/ask, but streams each agent step as it finishes (newline-delimited JSON), then the result."""
    events: queue.Queue = queue.Queue()

    def work() -> None:
        try:
            result = run_agent(
                req.question,
                language=req.language,
                quantity_quintals=req.quantity_quintals,
                transport_rate_per_km=req.transport_rate_per_km,
                on_step=lambda step: events.put({"type": "step", "step": step}),
            )
            events.put({"type": "result", "result": result})
        except Exception as exc:  # noqa: BLE001
            events.put({"type": "error", "error": f"{exc.__class__.__name__}"})
        finally:
            events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        while True:
            item = events.get()
            if item is None:
                break
            yield json.dumps(item, ensure_ascii=False, default=str) + "\n"

    return StreamingResponse(
        stream(), media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str | None = Form(None)) -> dict:
    data = await audio.read()
    if not data:
        raise HTTPException(400, "Empty recording.")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Recording too long. Please keep it under 30 seconds.")
    try:
        return voice.transcribe(data, audio.filename or "speech.webm", audio.content_type or "audio/webm", language)
    except voice.VoiceError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/speak")
def speak(req: SpeakRequest) -> dict:
    try:
        return {"audio_base64": voice.speak(req.text, req.language), "format": "wav"}
    except voice.VoiceError as exc:
        raise HTTPException(502, str(exc)) from exc


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
