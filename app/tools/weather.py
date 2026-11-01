"""7-day weather outlook and onion storage/transport risk, from Open-Meteo (no key).

Risk rules (transparent and sourced, see README):
- Humid day: daily mean relative humidity above STORAGE_RH_LIMIT_PCT (70%).
  Dry onions store best at 65-70% RH (UC Davis Postharvest Technology Center);
  higher humidity favours rot, mould and root growth.
- Rainy day: rain of RAINY_DAY_MM (2.5 mm) or more, the IMD definition of a rainy day.
  Rain also makes loading and transport to the mandi riskier.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

from app.config import settings
from app.http import UpstreamError, fetch_json

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
MET_HEADERS = {"User-Agent": "MandiMausam/1.0 (+https://github.com/KunalwritesCode/mandi-mausam)"}  # MET Norway asks for an identifying agent
IST = timezone(timedelta(hours=5, minutes=30))
_OM_COOLDOWN_S = 300          # after Open-Meteo refuses us (shared host IPs get 429), skip it for a few minutes
_om_down_until = 0.0


def _open_meteo_outlook(lat: float, lon: float, days: int) -> dict[str, Any]:
    params = {
        "latitude": round(float(lat), 4),
        "longitude": round(float(lon), 4),
        "daily": "precipitation_sum,precipitation_probability_max,temperature_2m_max",
        "hourly": "relative_humidity_2m",
        "forecast_days": days,
        "timezone": "Asia/Kolkata",
    }
    data, src = fetch_json(source_name="Open-Meteo Forecast API", url=FORECAST_URL, params=params, ttl_s=1800)
    return {"ok": True, **summarise(data), "source": src}


def _met_forecast(lat: float, lon: float) -> tuple[dict[str, Any], dict[str, Any]]:
    """MET Norway Locationforecast 2.0: free, no key, answers from any host. Used when Open-Meteo is unavailable."""
    params = {"lat": round(float(lat), 4), "lon": round(float(lon), 4)}
    data, src = fetch_json(
        source_name="MET Norway Locationforecast 2.0", url=MET_URL, params=params, headers=MET_HEADERS, ttl_s=1800
    )
    return data, src


def met_to_open_meteo_shape(data: dict[str, Any], days: int = 7) -> dict[str, Any]:
    """Re-shape a MET Norway forecast into the daily/hourly layout summarise() reads.

    Entries are hourly at first, then every 6 hours. Rain for an entry is its next-1-hour amount, or its
    next-6-hours amount when no 1-hour block exists, so nothing is counted twice. Days are Indian dates.
    MET Norway gives no rain-chance percentage, so that field stays empty rather than guessed.
    The first day only covers the hours still ahead.
    """
    hourly_t: list[str] = []
    hourly_rh: list[float | None] = []
    rain: dict[str, float] = {}
    tmax: dict[str, float] = {}
    for e in data["properties"]["timeseries"]:
        local = datetime.fromisoformat(e["time"].replace("Z", "+00:00")).astimezone(IST)
        day = local.strftime("%Y-%m-%d")
        inst = e["data"]["instant"]["details"]
        hourly_t.append(local.strftime("%Y-%m-%dT%H:%M"))
        hourly_rh.append(inst.get("relative_humidity"))
        if inst.get("air_temperature") is not None:
            tmax[day] = max(tmax.get(day, -99.0), inst["air_temperature"])
        block = e["data"].get("next_1_hours") or e["data"].get("next_6_hours")
        if block and block.get("details", {}).get("precipitation_amount") is not None:
            rain[day] = rain.get(day, 0.0) + block["details"]["precipitation_amount"]
        else:
            rain.setdefault(day, 0.0)
    all_days = sorted(set(t[:10] for t in hourly_t))[:days]
    return {
        "daily": {
            "time": all_days,
            "precipitation_sum": [round(rain.get(d, 0.0), 1) for d in all_days],
            "precipitation_probability_max": [None for _ in all_days],
            "temperature_2m_max": [tmax.get(d) for d in all_days],
        },
        "hourly": {"time": hourly_t, "relative_humidity_2m": hourly_rh},
    }


def get_weather_outlook(lat: float, lon: float, days: int = 7) -> dict[str, Any]:
    """7-day outlook. Open-Meteo first; if it refuses or fails, MET Norway. The source named in the answer is the one used."""
    global _om_down_until
    days = max(1, min(int(days), 14))
    errors: list[str] = []
    if time.time() >= _om_down_until:
        try:
            return _open_meteo_outlook(lat, lon, days)
        except UpstreamError as exc:
            errors.append(str(exc))
            _om_down_until = time.time() + _OM_COOLDOWN_S
    try:
        data, src = _met_forecast(lat, lon)
        return {"ok": True, **summarise(met_to_open_meteo_shape(data, days)), "source": src}
    except (UpstreamError, KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
        return {"ok": False, "error": " | ".join(errors)}


def summarise(data: dict[str, Any]) -> dict[str, Any]:
    """Turn an Open-Meteo response into per-day rows and a risk summary."""
    daily = data["daily"]
    hourly_t = data["hourly"]["time"]
    hourly_rh = data["hourly"]["relative_humidity_2m"]

    rh_by_day: dict[str, list[float]] = {}
    for t, rh in zip(hourly_t, hourly_rh):
        if rh is not None:
            rh_by_day.setdefault(t[:10], []).append(rh)

    rows = []
    for i, day in enumerate(daily["time"]):
        rain = daily["precipitation_sum"][i]
        prob = daily["precipitation_probability_max"][i]
        tmax = daily["temperature_2m_max"][i]
        rh_mean = round(mean(rh_by_day[day])) if rh_by_day.get(day) else None
        humid = rh_mean is not None and rh_mean > settings.storage_rh_limit_pct
        rainy = rain is not None and rain >= settings.rainy_day_mm
        rows.append(
            {
                "date": day,
                "rain_mm": rain,
                "rain_chance_pct": prob,
                "humidity_mean_pct": rh_mean,
                "temp_max_c": tmax,
                "humid": humid,
                "rainy": rainy,
                "risk": "high" if (humid and rainy) else ("medium" if (humid or rainy) else "low"),
            }
        )

    humid_days = [r["date"] for r in rows if r["humid"]]
    rainy_days = [r["date"] for r in rows if r["rainy"]]
    return {
        "days": rows,
        "summary": {
            "humid_days": len(humid_days),
            "rainy_days": len(rainy_days),
            "first_rainy_day": rainy_days[0] if rainy_days else None,
            "total_rain_mm": round(sum(r["rain_mm"] or 0 for r in rows), 1),
            "storage_rh_limit_pct": settings.storage_rh_limit_pct,
            "rainy_day_mm": settings.rainy_day_mm,
            "storage_risk": (
                "high" if len(humid_days) >= 4 else "medium" if len(humid_days) >= 2 else "low"
            ),
        },
    }


def _sky_from_met(data: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    e = data["properties"]["timeseries"][0]
    inst = e["data"]["instant"]["details"]
    local = datetime.fromisoformat(e["time"].replace("Z", "+00:00")).astimezone(IST)
    nxt = e["data"].get("next_1_hours", {}).get("details", {})
    return {
        "ok": True,
        "time": local.strftime("%Y-%m-%dT%H:%M"),
        "temperature_c": inst["air_temperature"],
        "humidity_pct": round(inst["relative_humidity"]),
        "rain_mm": nxt.get("precipitation_amount", 0) or 0,
        "cloud_cover_pct": round(inst["cloud_area_fraction"]),
        "wind_kmh": round(inst["wind_speed"] * 3.6, 1),
        "is_day": 6 <= local.hour < 18,   # approximation, only used to dim the picture after dark
        "humid_for_storage": inst["relative_humidity"] > settings.storage_rh_limit_pct,
        "source": src,
    }


def get_current_sky(lat: float, lon: float) -> dict[str, Any]:
    """Conditions right now, used to draw the live sky on the home page. Open-Meteo first, MET Norway as backup."""
    global _om_down_until
    errors: list[str] = []
    if time.time() >= _om_down_until:
        params = {
            "latitude": round(float(lat), 4),
            "longitude": round(float(lon), 4),
            "current": "temperature_2m,relative_humidity_2m,precipitation,cloud_cover,wind_speed_10m,is_day",
            "timezone": "Asia/Kolkata",
        }
        try:
            data, src = fetch_json(source_name="Open-Meteo Forecast API", url=FORECAST_URL, params=params, ttl_s=900)
            cur = data["current"]
            return {
                "ok": True,
                "time": cur["time"],
                "temperature_c": cur["temperature_2m"],
                "humidity_pct": cur["relative_humidity_2m"],
                "rain_mm": cur["precipitation"],
                "cloud_cover_pct": cur["cloud_cover"],
                "wind_kmh": cur["wind_speed_10m"],
                "is_day": bool(cur["is_day"]),
                "humid_for_storage": cur["relative_humidity_2m"] > settings.storage_rh_limit_pct,
                "source": src,
            }
        except (UpstreamError, KeyError, TypeError) as exc:
            errors.append(str(exc))
            if isinstance(exc, UpstreamError):
                _om_down_until = time.time() + _OM_COOLDOWN_S
    try:
        data, src = _met_forecast(lat, lon)
        return _sky_from_met(data, src)
    except (UpstreamError, KeyError, TypeError, ValueError, IndexError) as exc:
        errors.append(str(exc))
        return {"ok": False, "error": " | ".join(errors)}
