"""Parsing tests use the documented response *shapes* of each API with small hand-written inputs."""

from app.tools.geo import clean_market_name, haversine_km
from app.tools.mandi import normalise
from app.tools.weather import summarise


def test_market_name_cleaning():
    assert clean_market_name("Lasalgaon(Niphad)") == ["Lasalgaon", "Niphad"]
    assert clean_market_name("APMC Lasalgaon ") == ["Lasalgaon"]
    assert clean_market_name("Mumbai-Onion & Potato Market ")[0].startswith("Mumbai")
    assert clean_market_name("APMC Chattrapati Sambhajinagar ") == ["Chattrapati Sambhajinagar", "Aurangabad"]
    assert clean_market_name("Ahmednagar") == ["Ahmednagar", "Ahilyanagar"]


def test_record_normalise():
    rec = {"State": "Maharashtra", "District": "Nashik", "Market": "Lasalgaon", "Commodity": "Onion",
           "Variety": "Red", "Arrival_Date": "31/10/2026", "Min_Price": "1000", "Max_Price": "4500", "Modal_Price": "3900"}
    n = normalise(rec)
    assert n["arrival_date"] == "2026-10-31" and n["modal_price"] == 3900.0
    assert normalise({**rec, "Modal_Price": "0"}) is None


def test_weather_risk_rules():
    data = {
        "daily": {"time": ["2026-11-01", "2026-11-02"], "precipitation_sum": [3.5, 0.0],
                  "precipitation_probability_max": [80, 10], "temperature_2m_max": [28.6, 30.1]},
        "hourly": {"time": ["2026-11-01T00:00", "2026-11-01T12:00", "2026-11-02T00:00", "2026-11-02T12:00"],
                   "relative_humidity_2m": [96, 90, 60, 50]},
    }
    out = summarise(data)
    d1, d2 = out["days"]
    assert d1["rainy"] and d1["humid"] and d1["risk"] == "high"
    assert not d2["rainy"] and not d2["humid"] and d2["risk"] == "low"
    assert out["summary"]["first_rainy_day"] == "2026-11-01"


def test_haversine_sanity():
    # Lasalgaon to Nashik city is roughly 50-60 km in a straight line.
    assert 40 < haversine_km(20.15, 74.23, 19.99, 73.79) < 60


def test_current_sky_maps_open_meteo_fields(monkeypatch):
    from app.tools import weather
    payload = {"current": {"time": "2026-11-01T16:00", "temperature_2m": 24.1, "relative_humidity_2m": 78,
                           "precipitation": 0.4, "cloud_cover": 92, "wind_speed_10m": 11.5, "is_day": 1}}
    monkeypatch.setattr(weather, "fetch_json", lambda **kw: (payload, {"name": "Open-Meteo Forecast API"}))
    weather._om_down_until = 0.0
    out = weather.get_current_sky(20.15, 74.23)
    assert out["ok"] and out["humidity_pct"] == 78 and out["rain_mm"] == 0.4 and out["is_day"] is True
    assert out["humid_for_storage"] is True


def test_current_sky_reports_errors_instead_of_guessing(monkeypatch):
    from app.tools import weather
    def boom(**kw):
        raise weather.UpstreamError("timeout")
    monkeypatch.setattr(weather, "fetch_json", boom)
    weather._om_down_until = 0.0
    out = weather.get_current_sky(20.15, 74.23)
    assert out["ok"] is False and "timeout" in out["error"]


def test_sky_and_place_endpoints(monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as m
    seen = {}

    def fake_sky(lat, lon):
        seen["sky"] = (lat, lon)
        return {"ok": True, "humidity_pct": 70}

    monkeypatch.setattr(m.weather, "get_current_sky", fake_sky)
    monkeypatch.setattr(m.geo, "find_place", lambda q, state=None: {"found": True, "name": "Pune", "district": "Pune",
                                                                    "state": state, "lat": 18.52, "lon": 73.86, "source": {"name": "x"}})
    c = TestClient(m.app)
    assert c.get("/api/sky").json()["place"]["name"] == "Lasalgaon"          # default stays Lasalgaon
    r = c.get("/api/sky", params={"lat": 18.52, "lon": 73.86}).json()
    assert seen["sky"] == (18.52, 73.86) and r["place"] == {"lat": 18.52, "lon": 73.86}
    assert c.get("/api/sky", params={"lat": 51.5, "lon": -0.1}).status_code == 400   # outside India refused
    p = c.get("/api/place", params={"q": "Pune"}).json()
    assert p["found"] and p["state"] == "Maharashtra" and p["lat"] == 18.52
    assert c.get("/api/place", params={"q": ""}).status_code == 422
