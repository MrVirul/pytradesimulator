"""The security console summarizes audit rows for an administrator."""

from fastapi.testclient import TestClient

from secure_api.app.main import app


def _open(monkeypatch):
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
        "secure_api.app.web.routes.list_events",
        lambda *args, **kwargs: [
            {
                "request_id": "req-demo-limit-2",
                "client_id": "pytradesim-scenario",
                "action": "market-data:read",
                "resource": "/api/v1/market-data/BASELINE",
                "decision": "denied",
                "reason": "rate_limited",
                "status_code": 429,
                "latency_ms": 12,
                "recorded_at": "2026-10-23T00:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.security_metrics",
        lambda minutes: {
            "minutes": 15,
            "requests": 4,
            "allowed": 1,
            "denied": 3,
            "status_401": 0,
            "status_403": 1,
            "status_429": 2,
            "p50": 20.0,
            "p95": 40.0,
            "p99": 55.0,
            "per_minute": [{"minute": "2026-10-23T00:00:00+00:00", "count": 4, "width": 100}],
            "clients": [{"client_id": "pytradesim-scenario", "count": 3}],
            "policies": [
                {"subject": "*", "category": "market_data", "allowed": 60, "used": 4, "window_seconds": 60}
            ],
        },
    )


def test_security_page_shows_counts_and_links_the_request(monkeypatch):
    _open(monkeypatch)
    response = TestClient(app, base_url="https://testserver").get(
        "/ui/security",
        headers={"Cookie": "pytradesim_session=sess"},
    )
    assert response.status_code == 200
    text = response.text
    assert "429" in text
    assert "403" in text
    assert "p95" in text
    assert "40.0" in text
    assert 'href="/ui/audit?request_id=req-demo-limit-2"' in text
    assert "<select" in text
    assert "market_data" in text


def test_metrics_requires_operations_read(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REQUIRED", "0")
    monkeypatch.setenv("JWT_PUBLIC_KEY", "unused")
    monkeypatch.setattr(
        "secure_api.app.main.decode_token",
        lambda token: {"roles": ["market_data_client"], "client_id": "market", "exp": 9999999999},
    )
    response = TestClient(app, base_url="https://testserver").get(
        "/api/v1/metrics",
        headers={"Authorization": "Bearer token"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
