"""The market console shows depth, spread, freshness, and a stale book."""

from fastapi.testclient import TestClient

from secure_api.app.main import app


def _open(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REQUIRED", "0")
    monkeypatch.setattr(
        "secure_api.app.web.routes.load_session",
        lambda session_id: {
            "client_id": "market",
            "roles": ["market_data_client"],
            "access_token": "token",
            "csrf_token": "csrf",
            "id_token": "",
            "expires_at": None,
        },
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.decode_token",
        lambda token: {"roles": ["market_data_client"], "client_id": "market", "exp": 9999999999},
    )
    monkeypatch.setattr("secure_api.app.web.routes.feed_health", lambda: {"logged_on": True, "last_message_at": None})
    books = {
        "PRICE": {
            "symbol": "PRICE",
            "status": "live",
            "received_at": "2026-10-23T00:00:00+00:00",
            "ingest_sequence": 4,
            "bids": [{"price": 149.0, "quantity": 10}],
            "asks": [{"price": 151.0, "quantity": 5}],
        },
        "SPREAD": {
            "symbol": "SPREAD",
            "status": "stale",
            "received_at": "2026-10-23T00:00:00+00:00",
            "ingest_sequence": 2,
            "bids": [{"price": 50.0, "quantity": 10}],
            "asks": [{"price": 70.0, "quantity": 4}, {"price": 60.0, "quantity": 10}],
        },
        "VOLUME": {
            "symbol": "VOLUME",
            "status": "live",
            "received_at": "2026-10-23T00:00:00+00:00",
            "ingest_sequence": 9,
            "bids": [{"price": 100.0, "quantity": 4}],
            "asks": [{"price": 101.0, "quantity": 8}],
        },
    }
    monkeypatch.setattr(
        "secure_api.app.web.routes.list_symbols",
        lambda: [{"symbol": name, "status": book["status"], "received_at": book["received_at"]} for name, book in books.items()],
    )
    monkeypatch.setattr("secure_api.app.web.routes.get_symbol", lambda symbol: books.get(symbol))
    monkeypatch.setattr(
        "secure_api.app.web.routes.recent_trades",
        lambda symbol, limit: [{"ingestion_id": 1, "price": 151.0, "quantity": 10, "received_at": "2026-10-23T00:00:00+00:00", "ingest_sequence": 4}],
    )


def test_depth_spread_and_stale_label(monkeypatch):
    _open(monkeypatch)
    client = TestClient(app, base_url="https://testserver")
    page = client.get("/ui/market", params={"symbol": "SPREAD"}, headers={"Cookie": "pytradesim_session=sess"})
    assert page.status_code == 200
    assert "PRICE" in page.text and "VOLUME" in page.text
    assert "Status stale" in page.text
    assert "Spread" in page.text
    assert "10.0" in page.text
    assert "no event time" in page.text
    assert "data-poll" in page.text
    assert "!document.body.dataset.backoff" in page.text
    assert "data-age-from=" in page.text
    ladder = page.text.split('<div class="ladder', 1)[1]
    assert ladder.index("70.00") < ladder.index("60.00") < ladder.index("Spread") < ladder.index("50.00")
    assert 'data-k="best-bid"' in page.text
    assert "Identical prints in one exchange flush are collapsed." in page.text
    paused = client.get(
        "/ui/market-data/PRICE/book",
        params={"paused": "1"},
        headers={"Cookie": "pytradesim_session=sess"},
    )
    assert "Paused" in paused.text
    assert "every 3s" not in paused.text
    assert "Resume" in paused.text
    same = client.get(
        "/ui/market-data/PRICE/book",
        params={"since": "4", "st": "live", "lo": "1"},
        headers={"Cookie": "pytradesim_session=sess"},
    )
    assert same.status_code == 204
    assert same.text == ""
    moved = client.get(
        "/ui/market-data/PRICE/book",
        params={"since": "3", "st": "live", "lo": "1"},
        headers={"Cookie": "pytradesim_session=sess"},
    )
    assert moved.status_code == 200
    assert "Status live" in moved.text
    assert 'hx-swap-oob="outerHTML"' in moved.text
    assert 'data-id="1"' in moved.text
