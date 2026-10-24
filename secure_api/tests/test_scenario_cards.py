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
    monkeypatch.setattr(
        "secure_api.app.web.routes.recent_runs",
        lambda limit=12: [
            {
                "id": 3,
                "scenario": "volume",
                "status": "passed",
                "request_id": "req-demo",
                "created_at": "2026-10-23T00:00:00+00:00",
            }
        ],
    )
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
    assert "No order" in page.text
    assert "Budget 2 of 3 per 60s" in page.text
    assert "pending" in page.text
    assert 'name="price"' not in page.text
    assert 'id="confirm-run"' in page.text
    assert "every 3s" in page.text
    assert 'aria-live="polite"' in page.text
    assert 'href="/ui/audit?request_id=req-demo"' in page.text
    assert "10-23 00:00:00" in page.text


def _signed_in(monkeypatch):
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


def test_finished_run_links_to_the_alert_and_stops_polling(monkeypatch):
    _signed_in(monkeypatch)
    monkeypatch.setattr(
        "secure_api.app.web.routes.snapshot",
        lambda subject, roles: [{"category": "scenario", "used": 1, "allowed": 3, "resets_at": None}],
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.get_run",
        lambda run_id: {
            "id": run_id,
            "scenario": "price_movement",
            "status": "passed",
            "symbol": "PRICE",
            "request_id": "req-passed",
        },
    )
    client = TestClient(app, base_url="https://testserver")
    page = client.get("/ui/scenarios", params={"run": "4"}, headers={"Cookie": "pytradesim_session=sess"})
    assert page.status_code == 200
    assert "Alerts for PRICE" in page.text
    assert 'href="/ui/audit?request_id=req-passed"' in page.text
    assert "every 3s" not in page.text
    monkeypatch.setattr(
        "secure_api.app.web.routes.get_run",
        lambda run_id: {
            "id": run_id,
            "scenario": "price_movement",
            "status": "failed",
            "symbol": "PRICE",
            "request_id": "",
        },
    )
    failed = client.get("/ui/scenarios/runs/4", headers={"Cookie": "pytradesim_session=sess"})
    assert failed.status_code == 200
    assert "The scenario did not complete." in failed.text
    assert "every 3s" not in failed.text


def test_spent_budget_disables_run(monkeypatch):
    _signed_in(monkeypatch)
    monkeypatch.setattr(
        "secure_api.app.web.routes.snapshot",
        lambda subject, roles: [
            {
                "category": "scenario",
                "used": 3,
                "allowed": 3,
                "resets_at": "2026-10-23T00:01:00+00:00",
            }
        ],
    )
    monkeypatch.setattr("secure_api.app.web.routes.get_run", lambda run_id: None)
    page = TestClient(app, base_url="https://testserver").get(
        "/ui/scenarios",
        headers={"Cookie": "pytradesim_session=sess"},
    )
    assert page.status_code == 200
    assert "Budget 0 of 3 per 60s" in page.text
    assert "disabled" in page.text
    assert "Resets 00:01:00.000" in page.text
