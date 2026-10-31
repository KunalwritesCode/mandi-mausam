"""Voice in and out with Sarvam AI (Indian languages).

- Speech-to-text: POST https://api.sarvam.ai/speech-to-text (multipart, up to 30 s audio)
- Text-to-speech: POST https://api.sarvam.ai/text-to-speech (JSON, returns base64 WAV in `audios`)
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings

STT_URL = "https://api.sarvam.ai/speech-to-text"
TTS_URL = "https://api.sarvam.ai/text-to-speech"
LANG_CODES = {"en": "en-IN", "hi": "hi-IN", "mr": "mr-IN"}
MAX_TTS_CHARS = 1400


class VoiceError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not settings.sarvam_api_key:
        raise VoiceError("SARVAM_API_KEY is not set on the server.")
    return {"api-subscription-key": settings.sarvam_api_key}


def transcribe(audio: bytes, filename: str, content_type: str, language: str | None) -> dict[str, Any]:
    data = {"model": settings.sarvam_stt_model, "mode": "transcribe"}
    if language in LANG_CODES:
        data["language_code"] = LANG_CODES[language]
    try:
        with httpx.Client(timeout=40) as client:
            resp = client.post(
                STT_URL,
                headers=_headers(),
                data=data,
                files={"file": (filename or "speech.webm", audio, content_type or "audio/webm")},
            )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise VoiceError(f"Speech-to-text failed ({exc.response.status_code}): {exc.response.text[:200]}") from exc
    except httpx.HTTPError as exc:
        raise VoiceError(f"Speech-to-text unreachable: {exc}") from exc
    body = resp.json()
    return {"transcript": body.get("transcript", ""), "language_code": body.get("language_code")}


def speak(text: str, language: str) -> str:
    """Return base64 WAV audio for the text."""
    text = (text or "").strip()[:MAX_TTS_CHARS]
    if not text:
        raise VoiceError("Nothing to speak.")
    payload = {
        "text": text,
        "target_language_code": LANG_CODES.get(language, "en-IN"),
        "speaker": settings.sarvam_tts_speaker,
        "model": settings.sarvam_tts_model,
    }
    try:
        with httpx.Client(timeout=40) as client:
            resp = client.post(TTS_URL, headers=_headers(), json=payload)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise VoiceError(f"Text-to-speech failed ({exc.response.status_code}): {exc.response.text[:200]}") from exc
    except httpx.HTTPError as exc:
        raise VoiceError(f"Text-to-speech unreachable: {exc}") from exc
    audios = resp.json().get("audios") or []
    if not audios:
        raise VoiceError("Text-to-speech returned no audio.")
    return audios[0]
