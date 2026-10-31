"""A tiny SQLite cache that remembers *real* API responses and when they were fetched.

Two uses:
1. Speed: repeat questions within the TTL skip the network.
2. Resilience: if an API is down, the last real response can be served, clearly
   labelled with its original fetch time. Nothing is ever invented or pre-seeded.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any

from app.config import settings


@dataclass
class CacheHit:
    value: Any
    fetched_at: float  # unix seconds
    fresh: bool


class ResponseCache:
    def __init__(self, path: str | None = None) -> None:
        self._path = path or settings.cache_path
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS responses ("
                " key TEXT PRIMARY KEY, value TEXT NOT NULL, fetched_at REAL NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def get(self, key: str, ttl_s: float) -> CacheHit | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT value, fetched_at FROM responses WHERE key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        value, fetched_at = json.loads(row[0]), float(row[1])
        return CacheHit(value=value, fetched_at=fetched_at, fresh=(time.time() - fetched_at) < ttl_s)

    def set(self, key: str, value: Any) -> float:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO responses (key, value, fetched_at) VALUES (?, ?, ?)",
                (key, json.dumps(value), now),
            )
        return now


cache = ResponseCache()
