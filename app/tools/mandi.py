"""Live mandi (APMC) prices from data.gov.in's Agmarknet feed, and the mandi comparison tool.

Resource: "Current Daily Price of Various Commodities from Various Markets (Mandi)"
(Directorate of Marketing & Inspection, Ministry of Agriculture & Farmers Welfare).
Prices are in rupees per quintal (100 kg).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.config import settings
from app.http import UpstreamError, fetch_json
from app.tools import geo
from app.tools.pricing import net_prices

DATA_GOV_URL = "https://api.data.gov.in/resource/{rid}"


def _num(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _date(v: Any) -> str | None:
    s = str(v or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def normalise(record: dict[str, Any]) -> dict[str, Any] | None:
    r = {k.lower(): v for k, v in record.items()}
    modal = _num(r.get("modal_price"))
    arrival = _date(r.get("arrival_date"))
    if modal is None or modal <= 0 or not arrival or not r.get("market"):
        return None
    return {
        "market": str(r["market"]).strip(),
        "district": (r.get("district") or "").strip() or None,
        "state": (r.get("state") or "").strip() or None,
        "commodity": (r.get("commodity") or "").strip(),
        "variety": (r.get("variety") or "").strip() or None,
        "arrival_date": arrival,
        "min_price": _num(r.get("min_price")),
        "max_price": _num(r.get("max_price")),
        "modal_price": modal,
    }


def ping() -> dict[str, Any]:
    """One-record call to the same endpoint, for /api/health: shows whether the host can reach data.gov.in at all."""
    if not settings.data_gov_api_key:
        return {"ok": False, "error": "DATA_GOV_IN_API_KEY is not set on the server."}
    public = {"filters[state.keyword]": "Maharashtra", "filters[commodity]": "Onion"}
    params = {"api-key": settings.data_gov_api_key, "format": "json", "limit": 1, **public}
    try:
        data, src = fetch_json(
            source_name="data.gov.in – Agmarknet daily mandi prices",
            url=DATA_GOV_URL.format(rid=settings.mandi_resource_id),
            params=params, public_params=public, ttl_s=300,
        )
    except UpstreamError as exc:
        return {"ok": False, "error": str(exc)[:240]}
    return {"ok": True, "records_returned": len(data.get("records") or []), "fetched_at": src["fetched_at"]}


def get_mandi_prices(commodity: str, state: str, district: str | None = None) -> dict[str, Any]:
    """Latest reported prices for a commodity in a state (optionally one district)."""
    if not settings.data_gov_api_key:
        return {"ok": False, "error": "DATA_GOV_IN_API_KEY is not set on the server."}

    public = {"filters[state.keyword]": state, "filters[commodity]": commodity}
    if district:
        public["filters[district]"] = district
    params = {"api-key": settings.data_gov_api_key, "format": "json", "limit": 1000, **public}
    try:
        data, src = fetch_json(
            source_name="data.gov.in – Agmarknet daily mandi prices",
            url=DATA_GOV_URL.format(rid=settings.mandi_resource_id),
            params=params,
            public_params=public,
            ttl_s=1800,
        )
    except UpstreamError as exc:
        return {"ok": False, "error": str(exc)}

    rows = [n for n in (normalise(r) for r in data.get("records") or []) if n]
    # Keep the most recent report per (market, variety).
    latest: dict[tuple, dict] = {}
    for r in rows:
        k = (r["market"], r["variety"])
        if k not in latest or r["arrival_date"] > latest[k]["arrival_date"]:
            latest[k] = r
    today = date.today()
    out = []
    for r in latest.values():
        age = (today - date.fromisoformat(r["arrival_date"])).days
        out.append({**r, "age_days": age, "stale": age > settings.stale_after_days})
    out.sort(key=lambda r: -r["modal_price"])
    return {"ok": True, "count": len(out), "records": out, "source": src}


def compare_mandis(
    commodity: str,
    state: str,
    origin_lat: float,
    origin_lon: float,
    quantity_quintals: float | None = None,
    transport_rate_per_km: float | None = None,
    max_mandis: int | None = None,
) -> dict[str, Any]:
    """Nearest mandis that reported this commodity, with price after transport cost."""
    max_mandis = int(max_mandis or settings.max_mandis)
    prices = get_mandi_prices(commodity, state)
    if not prices.get("ok"):
        return prices
    if not prices["records"]:
        return {
            "ok": False,
            "error": f"No mandi in {state} has reported {commodity} recently on data.gov.in.",
            "source": prices.get("source"),
        }

    # One row per market: best-priced variety at its latest date.
    by_market: dict[str, dict] = {}
    for r in prices["records"]:
        m = by_market.get(r["market"])
        if not m or (r["arrival_date"], r["modal_price"]) > (m["arrival_date"], m["modal_price"]):
            by_market[r["market"]] = r

    located = geo.locate_markets([(m, r["district"], r["state"]) for m, r in by_market.items()])
    with_coords = []
    unlocated = []
    for name, r in by_market.items():
        loc = located.get(name)
        if loc:
            km = geo.haversine_km(origin_lat, origin_lon, loc["lat"], loc["lon"])
            with_coords.append({**r, "lat": loc["lat"], "lon": loc["lon"], "_straight_km": km})
        else:
            unlocated.append(name)

    nearest = sorted(with_coords, key=lambda r: r["_straight_km"])[:max_mandis]
    dist = geo.road_distances((origin_lat, origin_lon), [(r["lat"], r["lon"]) for r in nearest])
    for r, km, mins in zip(nearest, dist["km"], dist["minutes"]):
        r["distance_km"] = km
        r["drive_minutes"] = mins
        r.pop("_straight_km", None)

    ranked = net_prices(nearest, quantity_quintals, transport_rate_per_km)
    coverage_note = None
    with_km = [r for r in ranked if r.get("distance_km") is not None]
    if with_km:
        closest = min(with_km, key=lambda r: r["distance_km"])
        if closest["distance_km"] > 100:
            coverage_note = (f"The nearest mandi with a reported price is {str(closest['market']).strip()}, "
                             f"{closest['distance_km']:.0f} km away (reported {closest['arrival_date']}); "
                             "no closer mandi has a price on record.")
    return {
        "ok": True,
        "commodity": commodity,
        "state": state,
        "distance_method": dist["method"],
        "quantity_quintals": quantity_quintals,
        "transport_rate_per_km": transport_rate_per_km,
        "transport_cost_known": transport_rate_per_km is not None and quantity_quintals is not None,
        "mandis": ranked,
        "coverage_note": coverage_note,
        "mandis_not_located": unlocated[:20],
        "sources": [prices["source"], dist.get("source")],
    }
