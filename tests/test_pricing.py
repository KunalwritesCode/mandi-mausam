"""Unit tests for the price-after-transport maths. Inputs here are test fixtures, not app data."""

from app.tools.pricing import net_prices


def _m(name, price, km, stale=False):
    return {"market": name, "modal_price": price, "distance_km": km, "stale": stale}


def test_net_price_formula():
    rows = net_prices([_m("A", 4000, 10.0)], quantity_quintals=20, transport_rate_per_km=40)
    r = rows[0]
    assert r["trip_cost_rs"] == 400          # 40 x 10
    assert r["transport_per_quintal_rs"] == 20  # 400 / 20
    assert r["net_price_per_quintal_rs"] == 3980
    assert r["net_total_rs"] == 3980 * 20


def test_far_mandi_with_higher_price_can_lose():
    rows = net_prices([_m("Near", 3900, 5), _m("Far", 4000, 120)], quantity_quintals=10, transport_rate_per_km=40)
    # Far: 4000 - 40*120/10 = 3520; Near: 3900 - 20 = 3880
    assert [r["market"] for r in rows] == ["Near", "Far"]
    assert rows[0]["rank"] == 1


def test_without_rate_ranks_by_price_and_leaves_net_empty():
    rows = net_prices([_m("A", 3800, 5), _m("B", 4100, 50)], quantity_quintals=None, transport_rate_per_km=None)
    assert rows[0]["market"] == "B"
    assert rows[0]["net_price_per_quintal_rs"] is None


def test_stale_never_outranks_fresh():
    rows = net_prices([_m("Old", 9000, 5, stale=True), _m("New", 3000, 5)], None, None)
    assert rows[0]["market"] == "New"
