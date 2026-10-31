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
