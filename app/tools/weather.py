"""7-day weather outlook and onion storage/transport risk, from Open-Meteo (no key).

Risk rules (transparent and sourced, see README):
- Humid day: daily mean relative humidity above STORAGE_RH_LIMIT_PCT (70%).
  Dry onions store best at 65-70% RH (UC Davis Postharvest Technology Center);
  higher humidity favours rot, mould and root growth.
- Rainy day: rain of RAINY_DAY_MM (2.5 mm) or more, the IMD definition of a rainy day.
  Rain also makes loading and transport to the mandi riskier.
"""

from __future__ import annotations

from statistics import mean
from typing import Any

from app.config import settings
from app.http import UpstreamError, fetch_json

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def get_weather_outlook(lat: float, lon: float, days: int = 7) -> dict[str, Any]:
    days = max(1, min(int(days), 14))
    params = {
        "latitude": round(float(lat), 4),
        "longitude": round(float(lon), 4),
        "daily": "precipitation_sum,precipitation_probability_max,temperature_2m_max",
        "hourly": "relative_humidity_2m",
        "forecast_days": days,
        "timezone": "Asia/Kolkata",
    }
    try:
        data, src = fetch_json(
            source_name="Open-Meteo Forecast API", url=FORECAST_URL, params=params, ttl_s=1800
        )
    except UpstreamError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, **summarise(data), "source": src}


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
