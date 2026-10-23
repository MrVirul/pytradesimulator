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
    assert "current sequence is 9" in response.text
