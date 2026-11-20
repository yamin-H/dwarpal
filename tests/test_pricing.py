import json

import pytest
from fastapi.testclient import TestClient
from helpers import app_settings

from app.core.pricing import Price, PriceTable, load_price_table, validate_routing_prices
from app.main import create_app


def test_cost_math():
    table = PriceTable({"x": Price(0.15, 0.60)})
    assert table.cost_micros("x", 1000, 500) == 450  # 1000*0.15 + 500*0.60


def test_mock_models_are_free_and_unknown_models_have_no_price():
    table = PriceTable()
    assert table.cost_micros("mock-echo", 10, 10) == 0
    assert table.cost_micros("gpt-x", 10, 10) is None and not table.knows("gpt-x")


def test_load_price_table(tmp_path):
    f = tmp_path / "prices.json"
    f.write_text(json.dumps({"per_million_tokens": {"m": {"input": 1, "output": 2}}}))
    assert load_price_table(str(f)).cost_micros("m", 1, 1) == 3
    assert load_price_table("").knows("auto")


@pytest.mark.parametrize("payload", [
    {}, {"per_million_tokens": []}, {"per_million_tokens": {"m": {"input": 1}}},
    {"per_million_tokens": {"m": {"input": -1, "output": 1}}},
    {"per_million_tokens": {"m": "free"}},
])
def test_invalid_price_files_are_rejected(tmp_path, payload):
    f = tmp_path / "prices.json"
    f.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_price_table(str(f))


def test_unpriced_models_in_routing_chains_are_rejected():
    validate_routing_prices({"mock-fail": ["mock-echo"]}, PriceTable())
    with pytest.raises(ValueError, match="no price"):
        validate_routing_prices({"gpt-x": ["gemini-y"]}, PriceTable())


def test_startup_fails_when_a_fallback_has_no_price(tmp_path):
    routing = tmp_path / "routing.json"
    routing.write_text(json.dumps({"chains": {"gpt-4o-mini": ["gemini/gemini-2.0-flash"]}}))
    with pytest.raises(ValueError, match="no price"):
        create_app(app_settings(routing_config=str(routing)))
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps({"per_million_tokens": {
        "gpt-4o-mini": {"input": 0.1, "output": 0.2},
        "gemini/gemini-2.0-flash": {"input": 0.1, "output": 0.2},
    }}))
    TestClient(create_app(app_settings(routing_config=str(routing), prices_config=str(prices))))