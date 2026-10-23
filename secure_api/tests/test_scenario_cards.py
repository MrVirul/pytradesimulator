"""Scenario cards show the fixed orders and say when no order is sent."""

from fastapi.testclient import TestClient

from secure_api.app.main import app
from secure_api.app.services.scenarios import scenario_choices


def test_cards_describe_the_fixed_orders():
    cards = {card["name"]: card for card in scenario_choices()}
    assert "buy 10 @ 150" in cards["price_movement"]["orders"]
    assert cards["price_movement"]["expects"] == "price_movement on PRICE"
    assert cards["unauthorized_access"]["sends_order"] is False
    assert cards["rate_limit_abuse"]["sends_order"] is False
    assert cards["volume"]["sends_order"] is True


def test_lab_page_shows_orders_budget_and_a_live_run(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REQUIRED", "0")
    monkeypatch.setattr(
        "secure_api.app.web.routes.load_session",
        lambda session_id: {
            "client_id": "admin",
            "roles": ["security_admin"],
            "access_token": "token",
            "csrf_token": "csrf",
            "id_token": "",
            "expires_at": None,
        },
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.decode_token",
        lambda token: {"roles": ["security_admin"], "client_id": "admin", "exp": 9999999999},
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.scenario_policy",
        lambda: {"requests_allowed": 3, "window_seconds": 60},
    )
    monkeypatch.setattr("secure_api.app.web.routes.recent_runs", lambda limit=12: [])
    monkeypatch.setattr(
        "secure_api.app.web.routes.snapshot",
        lambda subject, roles: [{"category": "scenario", "used": 1, "allowed": 3, "resets_at": None}],
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.get_run",
        lambda run_id: {
            "id": run_id,
            "scenario": "price_movement",
            "status": "pending",
            "symbol": "PRICE",
            "request_id": "",
        },
    )
    page = TestClient(app, base_url="https://testserver").get(
        "/ui/scenarios",
        params={"run": "4"},
        headers={"Cookie": "pytradesim_session=sess"},
    )
    assert page.status_code == 200
    assert "buy 10 @ 150" in page.text
    assert "Does not send an order." in page.text
    assert "Remaining 2." in page.text
    assert "pending" in page.text
    assert 'name="price"' not in page.text
