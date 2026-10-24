"""The overview shows the signed-in role its own permissions and usage."""

from fastapi.testclient import TestClient

from secure_api.app.main import app


def _client():
    return TestClient(app, base_url="https://testserver")


def _open(monkeypatch, role):
    monkeypatch.setenv("RATE_LIMIT_REQUIRED", "0")
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
        "secure_api.app.web.routes.list_books",
        lambda: [
            {
                "symbol": "BASELINE",
                "status": "stale",
                "received_at": "2026-10-23T00:00:00+00:00",
                "ingest_sequence": 6,
                "bids": [{"price": 10, "quantity": 1}],
                "asks": [{"price": 12, "quantity": 1}],
            }
        ],
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.feed_health",
        lambda: {"logged_on": True, "last_message_at": None},
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
    assert "Last message not recorded" in market.text
    assert 'hx-get="/ui/overview/books"' in market.text
    assert "every 5s" in market.text
    assert "10.00" in market.text and "12.00" in market.text
    assert ">6</td>" in market.text
    books = client.get("/ui/overview/books", headers={"Cookie": "pytradesim_session=sess"})
    assert books.status_code == 200
    assert 'id="overview-books"' in books.text
    assert "BASELINE" in books.text
    _open(monkeypatch, "security_admin")
    admin = client.get("/ui", headers={"Cookie": "pytradesim_session=sess"})
    assert "scenarios:run" in admin.text
    assert "audit:read" in admin.text
