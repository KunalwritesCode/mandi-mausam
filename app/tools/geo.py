"""Place lookup and road distances.

- Geocoding: Open-Meteo Geocoding API (GeoNames data, no key), with OpenStreetMap
  Nominatim as a fallback for small villages.
- Distances: OSRM public routing server (OpenStreetMap roads). If routing is
  unavailable, we fall back to straight-line distance and say so explicitly.
"""

from __future__ import annotations

import math
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.http import UpstreamError, fetch_json

OPEN_METEO_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OSRM_TABLE = "https://router.project-osrm.org/table/v1/driving/"

_DAY = 24 * 3600

# Renamed cities: Agmarknet and GeoNames do not always use the same name. Each alias is tried after the
# original. Checked live on 2 Nov 2026: "Ahmednagar" no longer resolves inside Maharashtra, "Ahilyanagar" does.
PLACE_ALIASES = {
    "ahmednagar": "Ahilyanagar",
    "ahmadnagar": "Ahilyanagar",
    "chhatrapati sambhajinagar": "Aurangabad",
    "chattrapati sambhajinagar": "Aurangabad",
    "chhatrapati sambhaji nagar": "Aurangabad",
    "sambhajinagar": "Aurangabad",
    "dharashiv": "Osmanabad",
    "ahilyanagar": "Ahmednagar",
    "ahilya nagar": "Ahmednagar",
}


def clean_market_name(name: str) -> list[str]:
    """Turn an Agmarknet market name into place-name candidates.

    'Lasalgaon(Niphad)' -> ['Lasalgaon', 'Niphad']; 'APMC Lasalgaon ' -> ['Lasalgaon'].
    """
    raw = name.strip()
    inside = re.findall(r"\(([^)]*)\)", raw)
    outside = re.sub(r"\([^)]*\)", " ", raw)
    candidates = [outside, *inside]
    cleaned: list[str] = []
    for c in candidates:
        c = re.sub(r"\b(APMC|A\.P\.M\.C|Market|Yard|Mandi|Sub\s*Yard|F&V|Onion|Potato)\b", " ", c, flags=re.I)
        c = re.sub(r"[^A-Za-z\s.-]", " ", c)
        c = re.sub(r"\s+", " ", c).strip(" .-")
        if len(c) >= 3 and c.lower() not in {x.lower() for x in cleaned}:
            cleaned.append(c)
    for c in list(cleaned):
        alias = PLACE_ALIASES.get(c.lower())
        if alias and alias.lower() not in {x.lower() for x in cleaned}:
            cleaned.append(alias)
    return cleaned


def _pick(results: list[dict], state: str | None, district: str | None) -> dict | None:
    def score(r: dict) -> int:
        s = 0
        if state and (r.get("admin1") or "").lower() == state.lower():
            s += 2
        if district and district.lower() in ((r.get("admin2") or "") + (r.get("admin3") or "")).lower():
            s += 1
        return s

    in_state = [r for r in results if not state or (r.get("admin1") or "").lower() == state.lower()]
    pool = in_state or ([] if state else results)
    return max(pool, key=score) if pool else None


def find_place(query: str, state: str | None = None, district: str | None = None) -> dict[str, Any]:
    """Find a village/town in India. Returns name, district, state, lat, lon and source."""
    query = (query or "").strip()
    if not query:
        return {"found": False, "error": "Empty place name."}

    try:
        data, src = fetch_json(
            source_name="Open-Meteo Geocoding (GeoNames)",
            url=OPEN_METEO_GEOCODE,
            params={"name": query, "count": 10, "language": "en", "format": "json", "countryCode": "IN"},
            ttl_s=30 * _DAY,
        )
        best = _pick(data.get("results") or [], state, district)
        if best:
            return {
                "found": True,
                "name": best.get("name"),
                "district": best.get("admin2"),
                "state": best.get("admin1"),
                "lat": best["latitude"],
                "lon": best["longitude"],
                "source": src,
            }
    except UpstreamError:
        pass

    # Fallback: OpenStreetMap Nominatim (better coverage of small villages).
    q = ", ".join(x for x in [query, district, state, "India"] if x)
    try:
        data, src = fetch_json(
            source_name="OpenStreetMap Nominatim",
            url=NOMINATIM,
            params={"q": q, "format": "json", "countrycodes": "in", "limit": 3, "addressdetails": 1},
            ttl_s=30 * _DAY,
        )
    except UpstreamError as exc:
        return {"found": False, "error": f"Place lookup services unavailable: {exc}"}
    if data:
        top = data[0]
        addr = top.get("address", {})
        return {
            "found": True,
            "name": query,
            "district": addr.get("state_district") or addr.get("county"),
            "state": addr.get("state"),
            "lat": float(top["lat"]),
            "lon": float(top["lon"]),
            "source": src,
        }
    return {"found": False, "error": f"Could not find '{query}' in India. Ask the farmer for a nearby town."}


def locate_market(market: str, district: str | None, state: str | None) -> dict | None:
    """Best-effort coordinates for a mandi, from its Agmarknet name. None if unknown."""
    for candidate in clean_market_name(market):
        try:
            data, src = fetch_json(
                source_name="Open-Meteo Geocoding (GeoNames)",
                url=OPEN_METEO_GEOCODE,
                params={"name": candidate, "count": 10, "language": "en", "format": "json", "countryCode": "IN"},
                ttl_s=30 * _DAY,
            )
        except UpstreamError:
            continue
        best = _pick(data.get("results") or [], state, district)
        if best:
            return {"lat": best["latitude"], "lon": best["longitude"], "matched_name": best.get("name"), "source": src}
    return None


def locate_markets(markets: list[tuple[str, str | None, str | None]]) -> dict[str, dict | None]:
    """Geocode many markets in parallel. Keyed by market name."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda m: locate_market(*m), markets))
    return {m[0]: r for m, r in zip(markets, results)}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def road_distances(origin: tuple[float, float], points: list[tuple[float, float]]) -> dict[str, Any]:
    """Road distance (km) and drive time (min) from origin to each point, in one OSRM call.

    Falls back to straight-line km (method='straight_line') if routing fails.
    """
    if not points:
        return {"method": "none", "km": [], "minutes": [], "source": None}
    coords = ";".join(f"{lon:.5f},{lat:.5f}" for lat, lon in [origin, *points])
    try:
        data, src = fetch_json(
            source_name="OSRM routing (OpenStreetMap roads)",
            url=OSRM_TABLE + coords,
            params={"sources": "0", "annotations": "distance,duration"},
            ttl_s=7 * _DAY,
        )
        dist = data["distances"][0][1:]
        dur = data["durations"][0][1:]
        if any(d is None for d in dist):
            raise UpstreamError("route missing for some points")
        return {
            "method": "road",
            "km": [round(d / 1000, 1) for d in dist],
            "minutes": [round(t / 60) for t in dur],
            "source": src,
        }
    except (UpstreamError, KeyError, IndexError, TypeError):
        return {
            "method": "straight_line",
            "km": [round(haversine_km(origin[0], origin[1], la, lo), 1) for la, lo in points],
            "minutes": [None] * len(points),
            "source": {"name": "Straight-line distance (routing unavailable)", "url": None},
        }
