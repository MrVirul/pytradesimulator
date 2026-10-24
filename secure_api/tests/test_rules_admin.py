"""Only an admin can change a surveillance rule, and the change is audited."""

from fastapi.testclient import TestClient

from secure_api.app.main import app


def _session(role):
    return {
        "client_id": role,
        "roles": [role],
        "access_token": "token",
        "csrf_token": "csrf-1",
        "id_token": "",
        "expires_at": None,
    }


def _open(monkeypatch, role):
    monkeypatch.setenv("RATE_LIMIT_REQUIRED", "0")
    monkeypatch.setattr(
        "secure_api.app.web.routes.load_session",
        lambda session_id: _session(role),
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.decode_token",
        lambda token: {"roles": [role], "client_id": role, "exp": 9999999999},
    )


def test_analyst_cannot_edit_a_rule(monkeypatch):
    _open(monkeypatch, "surveillance_analyst")
    called = []
    monkeypatch.setattr(
        "secure_api.app.web.routes.update_rule",
        lambda name, threshold, enabled: called.append(name) or True,
    )
    response = TestClient(app, base_url="https://testserver").post(
        "/ui/rules",
        data={"csrf_token": "csrf-1", "name": "volume", "threshold": "10", "enabled": "1"},
        headers={"Cookie": "pytradesim_session=sess"},
    )
    assert response.status_code == 403
    assert called == []
    assert response.headers["content-type"].startswith("text/html")


def test_admin_edit_is_audited(monkeypatch):
    _open(monkeypatch, "security_admin")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.setattr("secure_api.app.web.routes.update_rule", lambda name, threshold, enabled: True)
    written = []
    monkeypatch.setattr("secure_api.app.main.write_event", lambda event: written.append(event))
    response = TestClient(app, base_url="https://testserver").post(
        "/ui/rules",
        data={"csrf_token": "csrf-1", "name": "volume", "threshold": "10", "enabled": "1"},
        headers={"Cookie": "pytradesim_session=sess"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert written
    assert written[0]["action"] == "rules:write"
    assert written[0]["reason"] == "administrative_change"
    assert written[0]["decision"] == "allowed"


def test_alert_page_shows_observed_against_threshold(monkeypatch):
    _open(monkeypatch, "surveillance_analyst")
    monkeypatch.setattr(
        "secure_api.app.web.routes.get_alert",
        lambda alert_id: {
            "id": 7,
            "rule_name": "spread_widening",
            "symbol": "SPREAD",
            "severity": "warning",
            "observed_value": 10.0,
            "threshold": 5.0,
            "created_at": "2026-10-23T00:00:00+00:00",
            "detail": "spread 10",
            "ingest_sequence": 3,
        },
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.alert_context",
        lambda alert: {"book": None, "current_sequence": 9, "trades": []},
    )
    response = TestClient(app, base_url="https://testserver").get(
        "/ui/alerts/7",
        headers={"Cookie": "pytradesim_session=sess"},
    )
    assert response.status_code == 200
    assert "10.0" in response.text
    assert "5.0" in response.text
    assert "+5.00" in response.text
    assert "2.00×" in response.text
    assert "current sequence is 9" in response.text
    assert 'href="/ui/market?symbol=SPREAD"' in response.text


def _rules_page(monkeypatch, role):
    _open(monkeypatch, role)
    monkeypatch.setattr(
        "secure_api.app.web.routes.list_alerts",
        lambda symbol, severity, rule_name, created_from="", created_to="": [
            {
                "id": 4,
                "rule_name": "spread_widening",
                "symbol": "SPREAD",
                "severity": "warning",
                "observed_value": 12.5,
                "threshold": 10.0,
                "created_at": "2026-10-23T00:00:00+00:00",
                "detail": "spread crossed the threshold by a wide margin",
                "ingest_sequence": 2,
            }
        ],
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.filter_choices",
        lambda: {"symbols": ["SPREAD"], "rules": ["spread_widening"], "severities": ["warning"]},
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.list_rules",
        lambda: [{"name": "spread_widening", "enabled": True, "threshold": 10.0, "window_seconds": 30}],
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.timeline",
        lambda: [
            {"at": "2026-10-23T00:00:02+00:00", "kind": "alert", "label": "spread_widening", "ref": "4"},
            {"at": "2026-10-23T00:00:01+00:00", "kind": "scenario", "label": "price_movement", "ref": "8"},
        ],
    )
    return TestClient(app, base_url="https://testserver").get(
        "/ui/alerts",
        headers={"Cookie": "pytradesim_session=sess"},
    )


def test_analyst_sees_excess_and_cannot_edit_a_rule_on_the_page(monkeypatch):
    page = _rules_page(monkeypatch, "surveillance_analyst")
    assert page.status_code == 200
    assert "+2.50" in page.text
    assert "Latest 100 matching." in page.text
    assert 'hx-get="/ui/alerts/rows"' in page.text
    assert "every 10s" in page.text
    assert "visibilityState" in page.text
    assert 'data-id="4"' in page.text
    assert 'href="/ui/alerts/4"' in page.text
    assert 'href="/ui/scenarios?run=8"' in page.text
    assert "over 30s" in page.text
    assert 'name="threshold"' not in page.text
    assert "disabled" not in page.text


def test_admin_rule_form_stays_a_post(monkeypatch):
    page = _rules_page(monkeypatch, "security_admin")
    assert page.status_code == 200
    assert 'action="/ui/rules"' in page.text
    assert 'name="threshold"' in page.text
    assert 'type="number"' in page.text
    assert 'name="csrf_token"' in page.text


def test_alert_detail_draws_the_ladder(monkeypatch):
    _open(monkeypatch, "surveillance_analyst")
    monkeypatch.setattr(
        "secure_api.app.web.routes.get_alert",
        lambda alert_id: {
            "id": 7,
            "rule_name": "spread_widening",
            "symbol": "SPREAD",
            "severity": "warning",
            "observed_value": 10.0,
            "threshold": 5.0,
            "created_at": "2026-10-23T00:00:00+00:00",
            "detail": "spread 10",
            "ingest_sequence": 3,
        },
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.alert_context",
        lambda alert: {
            "book": {
                "bids": [{"price": 50, "quantity": 4}],
                "asks": [{"price": 60, "quantity": 10}],
            },
            "current_sequence": 3,
            "trades": [
                {
                    "ingestion_id": 11,
                    "price": 55,
                    "quantity": 2,
                    "received_at": "2026-10-23T00:00:03+00:00",
                }
            ],
        },
    )
    response = TestClient(app, base_url="https://testserver").get(
        "/ui/alerts/7",
        headers={"Cookie": "pytradesim_session=sess"},
    )
    assert response.status_code == 200
    ladder = response.text.split('<div class="ladder"', 1)[1]
    assert ladder.index("60.00") < ladder.index("50.00")
    assert "[{'price'" not in response.text
    assert "Trades at sequence 3" in response.text
    assert "55.00" in response.text


def test_audit_rule_links_to_status_without_a_book(monkeypatch):
    _open(monkeypatch, "surveillance_analyst")
    monkeypatch.setattr(
        "secure_api.app.web.routes.get_alert",
        lambda alert_id: {
            "id": 9,
            "rule_name": "api_abuse",
            "symbol": None,
            "severity": "warning",
            "observed_value": 4.0,
            "threshold": 2.0,
            "created_at": "2026-10-23T00:00:00+00:00",
            "detail": "client demo-market exceeded 429",
            "ingest_sequence": None,
        },
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.alert_context",
        lambda alert: {"book": None, "current_sequence": None, "trades": []},
    )
    response = TestClient(app, base_url="https://testserver").get(
        "/ui/alerts/9",
        headers={"Cookie": "pytradesim_session=sess"},
    )
    assert response.status_code == 200
    evidence = response.text.split("<h2>Evidence</h2>", 1)[1]
    assert "Rule computed from audit events; no book." in evidence
    assert 'href="/ui/audit?status_code=429"' in evidence
    assert "demo-market" not in evidence
    assert "current sequence" not in evidence
    monkeypatch.setattr(
        "secure_api.app.web.routes.get_alert",
        lambda alert_id: {
            "id": 10,
            "rule_name": "access_denied",
            "symbol": None,
            "severity": "warning",
            "observed_value": 6.0,
            "threshold": 5.0,
            "created_at": "2026-10-23T00:00:00+00:00",
            "detail": "client demo-market exceeded 403",
            "ingest_sequence": None,
        },
    )
    denied = TestClient(app, base_url="https://testserver").get(
        "/ui/alerts/10",
        headers={"Cookie": "pytradesim_session=sess"},
    )
    assert 'href="/ui/audit?status_code=403"' in denied.text
