"""The harness accepts a scenario name and no free-form order."""

import pytest

from secure_api.harness.scenarios import (
    ScenarioError,
    orders_for,
    parse_request,
    resolve_scenario,
)


def test_each_named_scenario_has_fixed_orders():
    symbol, orders = orders_for("price_movement")
    assert symbol == "PRICE"
    assert orders == [
        {"side": "buy", "quantity": 10, "price": 150, "expect": "0"},
        {"side": "sell", "quantity": 10, "price": 150, "expect": "2"},
    ]
    symbol, orders = orders_for("spread_widening")
    assert symbol == "SPREAD"
    assert [order["price"] for order in orders] == [50, 60]
    assert [order["expect"] for order in orders] == ["0", "0"]
    symbol, orders = orders_for("volume")
    assert symbol == "VOLUME"
    fills = [order for order in orders if order["expect"] == "2"]
    assert sum(order["quantity"] for order in fills) == 1050
    assert [order.get("pause_after") for order in fills] == [2, 2, None]
    prices = [order["price"] for order in orders]
    assert len(set(prices)) > 1


def test_request_accepts_only_the_scenario_name():
    assert parse_request({"scenario": "volume"}) == "volume"
    assert resolve_scenario([], {"SCENARIO": "spread_widening"}) == "spread_widening"
    with pytest.raises(ScenarioError) as unknown:
        parse_request({"scenario": "custom"})
    assert unknown.value.reason == "unknown_scenario"
    with pytest.raises(ScenarioError) as extra:
        parse_request(
            {
                "scenario": "price_movement",
                "symbol": "BASELINE",
                "side": "buy",
                "price": 1,
                "quantity": 5,
            }
        )
    assert extra.value.reason == "free_form_order"
    with pytest.raises(ScenarioError) as orders:
        parse_request({"orders": [{"price": 1}]})
    assert orders.value.reason == "free_form_order"
    with pytest.raises(ScenarioError) as arguments:
        resolve_scenario(["price_movement", "150"], {})
    assert arguments.value.reason == "free_form_order"


def test_environment_order_fields_do_not_change_the_orders():
    name = resolve_scenario(
        [],
        {
            "SCENARIO": "price_movement",
            "ORDER_SYMBOL": "HACK",
            "ORDER_PRICE": "1",
            "ORDER_QTY": "9",
        },
    )
    symbol, orders = orders_for(name)
    assert symbol == "PRICE"
    assert orders[0]["price"] == 150
    assert orders[0]["quantity"] == 10
