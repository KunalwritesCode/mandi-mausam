"""Shared HTTP helper: timeouts, one retry, caching, and source attribution.

Every tool result carries a `source` block (name, public URL without secrets,
fetch time, and whether it came from the cache), so the UI can show where each
number came from.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.cache import cache
from app.config import settings

USER_AGENT = "MandiMausamAgent/0.1 (Forge hackathon prototype; github.com)"


_SECRET = re.compile(r"(api[-_]?key|key|token)=[^&\s'\"]+", re.IGNORECASE)


def scrub(text: str) -> str:
    """Remove API keys from text that may be shown to users (httpx error messages include the full URL)."""
    return _SECRET.sub(lambda m: f"{m.group(1)}=***", str(text))


class UpstreamError(RuntimeError):
    """An external API failed and no cached real response was available."""


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def fetch_json(
    *,
    source_name: str,
    url: str,
    params: dict[str, Any] | None = None,
    public_params: dict[str, Any] | None = None,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: Any = None,
    ttl_s: float = 600,
    cache_key: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Fetch JSON with caching. Returns (data, source_meta).

    `public_params` is what we show users as the query (no API keys).
    On failure, falls back to the last real cached response if one exists.
    """
    key = cache_key or f"{method}:{url}:{sorted((public_params or params or {}).items())}:{json_body}"
    hit = cache.get(key, ttl_s)
    if hit and hit.fresh:
        return hit.value, _meta(source_name, url, public_params, hit.fetched_at, from_cache=True)

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with httpx.Client(timeout=settings.http_timeout_s, headers={"User-Agent": USER_AGENT}) as client:
                resp = client.request(method, url, params=params, headers=headers, json=json_body)
            resp.raise_for_status()
            data = resp.json()
            fetched_at = cache.set(key, data)
            return data, _meta(source_name, url, public_params, fetched_at, from_cache=False)
        except (httpx.HTTPError, ValueError) as exc:  # ValueError: bad JSON
            last_error = exc
            if isinstance(exc, httpx.HTTPStatusError) and 400 <= exc.response.status_code < 500:
                break  # 429 / 403 / 404: asking again straight away will not help
            time.sleep(0.6 * (attempt + 1))

    if hit:  # stale but real
        meta = _meta(source_name, url, public_params, hit.fetched_at, from_cache=True)
        meta["stale_fallback"] = True
        meta["error"] = scrub(last_error)
        return hit.value, meta
    raise UpstreamError(f"{source_name} unavailable: {scrub(last_error)}")


def _meta(name: str, url: str, public_params: dict | None, fetched_at: float, from_cache: bool) -> dict:
    return {
        "name": name,
        "url": url,
        "query": public_params or {},
        "fetched_at": iso(fetched_at),
        "from_cache": from_cache,
    }
