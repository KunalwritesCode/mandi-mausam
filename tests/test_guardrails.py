from app.agent import guardrails as g


def test_rejects_empty_and_long():
    assert g.clean_question("   ")[1]
    assert g.clean_question("x" * 700)[1]
    assert g.clean_question("Sell onion?")[0] == "Sell onion?"


def test_numbers_parsing_handles_indian_commas_and_devanagari():
    assert g.numbers_in("₹3,900 per quintal, 1,20,000 total") == {3900.0, 120000.0}
    assert g.numbers_in("४५०० रुपये") == {4500.0}


def test_grounding_flags_invented_numbers():
    tool = [{"mandis": [{"modal_price": 3900, "distance_km": 12.4}]}]
    allowed = g.allowed_numbers(tool, {"q": "20 quintals"})
    assert g.unsupported_numbers("Sell at 3,900 rupees, 12.4 km away", allowed) == []
    assert g.unsupported_numbers("Prices will reach 5200 next week", allowed) == [5200.0]


def test_small_counts_allowed():
    allowed = g.allowed_numbers([], {})
    assert g.unsupported_numbers("Rain on 3 of the next 7 days", allowed) == []


def test_kisan_call_centre_number_is_allowed():
    allowed = g.allowed_numbers([], {})
    assert g.unsupported_numbers("Please call the Kisan Call Centre on 1800-180-1551.", allowed) == []


def test_precheck_asks_instead_of_guessing():
    assert g.precheck("sell?", None)
    assert g.precheck("onion near Lasalgaon, 0 quintals. Sell?", None)
    assert g.precheck("मेरे पास ० क्विंटल प्याज़ है, लासलगाँव में", None, "hi")
    assert g.precheck("I have 20 quintals of onion near Lasalgaon", 0)
    assert g.precheck("I have 20 quintals of onion near Lasalgaon. Sell?", 20) is None
    assert "क्विंटल" in g.precheck("बेचूँ?", None, "hi")


def test_derived_totals_are_allowed_but_invented_numbers_are_not():
    tool = [{"mandis": [{"modal_price": 2000, "net_price_per_quintal_rs": 1429}]}]
    allowed = g.allowed_numbers(tool, {"q": "I have 25 quintals", "qty": 25})
    assert g.unsupported_numbers("Total about 35,725 rupees (25 x 1,429)", allowed) == []
    big = g.allowed_numbers([{"mandis": [{"net_price_per_quintal_rs": 4499}]}], {"q": "5000 quintals", "qty": 5000})
    assert g.unsupported_numbers("About Rs 2.25 crore", big) == []
    assert g.unsupported_numbers("Prices will reach 5200 next week", allowed) == [5200.0]
