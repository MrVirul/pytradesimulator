"""The overview shows the signed-in role its own permissions and usage."""

from fastapi.testclient import TestClient

from secure_api.app.main import app


def _client():
    return TestClient(app, base_url="https://testserver")


def _open(monkeypatch, role):
    monkeypatch.setattr(
        "secure_api.app.web.routes.load_session",
        lambda session_id: {
            "client_id": role,
            "roles": [role],
            "access_token": "token",
            "csrf_token": "csrf",
            "id_token": "",
            "expires_at": None,
        },
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.decode_token",
        lambda token: {"roles": [role], "client_id": role, "exp": 9999999999},
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.list_symbols",
        lambda: [
            {
                "symbol": "BASELINE",
                "status": "stale",
                "received_at": "2026-10-23T00:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.get_symbol",
        lambda symbol: {"bids": [{"price": 10, "quantity": 1}], "asks": [{"price": 12, "quantity": 1}]},
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.feed_health",
        lambda: {"logged_on": True, "last_message_at": "2026-10-23T00:00:01+00:00"},
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.snapshot",
        lambda subject, roles: [{"category": "market_data", "used": 2, "allowed": 60, "resets_at": None}],
    )


def test_overview_is_scoped_to_the_role(monkeypatch):
    client = _client()
    _open(monkeypatch, "market_data_client")
    market = client.get("/ui", headers={"Cookie": "pytradesim_session=sess"})
    assert "market-data:read" in market.text
    assert "alerts:read" not in market.text
    assert "market_data" in market.text
    assert "2 of 60" in market.text
    assert "stale" in market.text
    _open(monkeypatch, "security_admin")
    admin = client.get("/ui", headers={"Cookie": "pytradesim_session=sess"})
    assert "scenarios:run" in admin.text
    assert "audit:read" in admin.text
