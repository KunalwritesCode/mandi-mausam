"""Runtime settings, read from environment variables (or a local .env file).

Nothing here is data: every price, forecast and distance the app shows is fetched
live from an official or public API at request time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass(frozen=True)
class Settings:
    # --- LLM (any OpenAI-compatible endpoint; Gemini by default) ---
    llm_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    llm_base_url: str = field(
        default_factory=lambda: _env(
            "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
    )
    llm_model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-flash-latest"))
    llm_max_steps: int = field(default_factory=lambda: int(_env("AGENT_MAX_STEPS", "6")))

    # --- Mandi prices: data.gov.in Open Government Data API (Agmarknet feed) ---
    data_gov_api_key: str = field(default_factory=lambda: _env("DATA_GOV_IN_API_KEY"))
    mandi_resource_id: str = field(
        default_factory=lambda: _env(
            "MANDI_RESOURCE_ID", "9ef84268-d588-465a-a308-a864a43d0070"
        )
    )

    # --- Voice: Sarvam AI speech-to-text and text-to-speech ---
    sarvam_api_key: str = field(default_factory=lambda: _env("SARVAM_API_KEY"))
    sarvam_stt_model: str = field(default_factory=lambda: _env("SARVAM_STT_MODEL", "saaras:v3"))
    sarvam_tts_model: str = field(default_factory=lambda: _env("SARVAM_TTS_MODEL", "bulbul:v3"))
    sarvam_tts_speaker: str = field(default_factory=lambda: _env("SARVAM_TTS_SPEAKER", "shubh"))

    # --- Decision rules (each one documented in README with its source) ---
    # UC Davis Postharvest Center: dry onions store best at 65-70% relative humidity;
    # higher humidity favours rot and root growth.
    storage_rh_limit_pct: float = field(
        default_factory=lambda: float(_env("STORAGE_RH_LIMIT_PCT", "70"))
    )
    # IMD defines a "rainy day" as a day with 2.5 mm or more of rain.
    rainy_day_mm: float = field(default_factory=lambda: float(_env("RAINY_DAY_MM", "2.5")))
    # Prices older than this many days are flagged as stale in the answer.
    stale_after_days: int = field(default_factory=lambda: int(_env("STALE_AFTER_DAYS", "3")))

    # --- Infrastructure ---
    cache_path: str = field(default_factory=lambda: _env("CACHE_PATH", "cache.sqlite3"))
    http_timeout_s: float = field(default_factory=lambda: float(_env("HTTP_TIMEOUT_S", "12")))
    max_mandis: int = field(default_factory=lambda: int(_env("MAX_MANDIS", "8")))


settings = Settings()
