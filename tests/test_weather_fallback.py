"""Open-Meteo refuses shared host addresses (429), so MET Norway is the backup. These tests use small payloads in the
same shape as the real MET Norway response (checked live against Lasalgaon on 1 Nov 2026)."""

import httpx
import pytest

from app.tools import weather
from app import http as app_http


def entry(utc, rh, temp=25.0, n1=None, n6=None, cloud=50.0, wind=2.0):
    data = {"instant": {"details": {"relative_humidity": rh, "air_temperature": temp,
                                    "cloud_area_fraction": cloud, "wind_speed": wind}}}
    if n1 is not None:
        data["next_1_hours"] = {"details": {"precipitation_amount": n1}}
    if n6 is not None:
        data["next_6_hours"] = {"details": {"precipitation_amount": n6}}
    return {"time": utc, "data": data}


MET = {"properties": {"timeseries": [
    entry("2026-11-01T11:00:00Z", 72, temp=26, n1=0.6, n6=1.9),     # 16:30 IST, 1 Nov
    entry("2026-11-01T12:00:00Z", 74, n1=1.0),                      # 17:30 IST
    entry("2026-11-01T19:00:00Z", 80, n1=0.0),                      # 00:30 IST, 2 Nov
    entry("2026-11-03T00:00:00Z", 60, temp=31, n6=3.0),             # 05:30 IST, 3 Nov, six-hourly step
]}}


@pytest.fixture(autouse=True)
def reset_cooldown():
    weather._om_down_until = 0.0
    yield
    weather._om_down_until = 0.0


def test_met_reshaped_to_indian_dates_without_double_counting_rain():
    out = weather.met_to_open_meteo_shape(MET)
    assert out["daily"]["time"] == ["2026-11-01", "2026-11-02", "2026-11-03"]
    assert out["daily"]["precipitation_sum"] == [1.6, 0.0, 3.0]          # 0.6 + 1.0, then 0, then the 6 h block
    assert out["daily"]["precipitation_probability_max"] == [None, None, None]   # never guessed
    assert out["hourly"]["time"][2] == "2026-11-02T00:30"


def test_met_feeds_the_same_risk_rules():
    rows = weather.summarise(weather.met_to_open_meteo_shape(MET))["days"]
    assert rows[0]["humid"] is True and rows[0]["humidity_mean_pct"] == 73      # mean of 72 and 74
    assert rows[2]["rainy"] is True and rows[2]["humid"] is False


def test_falls_back_to_met_when_open_meteo_returns_429(monkeypatch):
    calls = {"om": 0}

    def fake(**kw):
        if kw["url"] == weather.FORECAST_URL:
            calls["om"] += 1
            raise weather.UpstreamError("429 Too Many Requests")
        return MET, {"name": "MET Norway Locationforecast 2.0"}

    monkeypatch.setattr(weather, "fetch_json", fake)
    out = weather.get_weather_outlook(20.14, 74.24)
    assert out["ok"] and out["source"]["name"] == "MET Norway Locationforecast 2.0"
    assert len(out["days"]) == 3
    weather.get_weather_outlook(20.14, 74.24)                 # within the cool-down: Open-Meteo is not asked again
    assert calls["om"] == 1


def test_reports_both_errors_when_both_sources_fail(monkeypatch):
    def fake(**kw):
        raise weather.UpstreamError("down " + kw["url"].split("/")[2])

    monkeypatch.setattr(weather, "fetch_json", fake)
    out = weather.get_weather_outlook(20.14, 74.24)
    assert out["ok"] is False and "open-meteo" in out["error"] and "met.no" in out["error"]


def test_sky_falls_back_to_met_first_entry(monkeypatch):
    def fake(**kw):
        if kw["url"] == weather.FORECAST_URL:
            raise weather.UpstreamError("429")
        return MET, {"name": "MET Norway Locationforecast 2.0"}

    monkeypatch.setattr(weather, "fetch_json", fake)
    sky = weather.get_current_sky(20.14, 74.24)
    assert sky["ok"] and sky["time"] == "2026-11-01T16:30" and sky["rain_mm"] == 0.6
    assert sky["wind_kmh"] == 7.2 and sky["humid_for_storage"] is True and sky["is_day"] is True


def test_client_errors_are_not_retried(monkeypatch):
    seen = {"n": 0}

    def handler(request):
        seen["n"] += 1
        return httpx.Response(429, json={"error": "slow down"})

    real = httpx.Client
    monkeypatch.setattr(app_http.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(app_http.UpstreamError):
        app_http.fetch_json(source_name="t", url="https://example.invalid/never-cached-429", params={"x": 1})
    assert seen["n"] == 1


def test_api_keys_never_appear_in_error_messages():
    msg = "Client error '403 Forbidden' for url 'https://api.data.gov.in/resource/x?api-key=SECRET123&format=json&limit=1'"
    out = app_http.scrub(msg)
    assert "SECRET123" not in out and "api-key=***" in out and "format=json" in out
