"""Parsing tests use the documented response *shapes* of each API with small hand-written inputs."""

from app.tools.geo import clean_market_name, haversine_km
from app.tools.mandi import normalise
from app.tools.weather import summarise


def test_market_name_cleaning():
    assert clean_market_name("Lasalgaon(Niphad)") == ["Lasalgaon", "Niphad"]
    assert clean_market_name("APMC Lasalgaon ") == ["Lasalgaon"]
    assert clean_market_name("Mumbai-Onion & Potato Market ")[0].startswith("Mumbai")


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
