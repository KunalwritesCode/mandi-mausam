"""Price-after-transport arithmetic. Pure functions: all money maths happens here, never in the LLM.

Transport cost model (stated to the farmer in the UI):
    trip cost (Rs)              = transport_rate_per_km x one-way road distance (km)
    transport per quintal (Rs)  = trip cost / quantity (quintals)
    net price per quintal (Rs)  = modal price - transport per quintal
The farmer enters a per-km rate that already includes the return trip if their
vehicle owner charges for it. We never assume a rate.
"""

from __future__ import annotations

from typing import Any


def net_prices(
    mandis: list[dict[str, Any]],
    quantity_quintals: float | None,
    transport_rate_per_km: float | None,
) -> list[dict[str, Any]]:
    """Add trip cost and net price to each mandi and rank them.

    Without both quantity and rate, rows are ranked by modal price and the
    transport fields stay None (the agent must then ask the farmer).
    """
    known = (
        quantity_quintals is not None
        and transport_rate_per_km is not None
        and quantity_quintals > 0
        and transport_rate_per_km >= 0
    )
    out = []
    for m in mandis:
        row = dict(m)
        km = row.get("distance_km")
        if known and km is not None:
            trip = round(transport_rate_per_km * km)
            per_q = round(trip / quantity_quintals)
            row["trip_cost_rs"] = trip
            row["transport_per_quintal_rs"] = per_q
            row["net_price_per_quintal_rs"] = round(row["modal_price"] - per_q)
            row["net_total_rs"] = round(row["net_price_per_quintal_rs"] * quantity_quintals)
        else:
            row["trip_cost_rs"] = None
            row["transport_per_quintal_rs"] = None
            row["net_price_per_quintal_rs"] = None
            row["net_total_rs"] = None
        out.append(row)

    key = "net_price_per_quintal_rs" if known else "modal_price"
    # Fresh reports first, then by value; stale prices never outrank fresh ones.
    out.sort(key=lambda r: (bool(r.get("stale")), -(r[key] if r[key] is not None else float("-inf"))))
    for i, r in enumerate(out, start=1):
        r["rank"] = i
    return out
