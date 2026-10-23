"""Fragment requests stay in the page when the session or the limit fails."""

from fastapi.testclient import TestClient

from secure_api.app.auth.rate_limit import RateDecision
from secure_api.app.main import app


def _client():
    return TestClient(app, base_url="https://testserver")


def test_expired_fragment_redirects_without_the_login_page(monkeypatch):
    monkeypatch.setattr("secure_api.app.web.routes.load_session", lambda session_id: None)
    response = _client().get(
        "/ui/market-data/BASELINE/book",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert response.headers["hx-redirect"].endswith("/ui/login?error=expired")
    assert "Sign in" not in response.text
    assert 'href="/ui/login/start"' not in response.text


def test_limit_fragment_keeps_polling(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_REQUIRED", "1")
    monkeypatch.setattr(
        "secure_api.app.web.routes.load_session",
        lambda session_id: {
            "client_id": "market",
            "roles": ["market_data_client"],
            "access_token": "token",
            "csrf_token": "csrf",
            "id_token": "",
        },
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.decode_token",
        lambda token: {"roles": ["market_data_client"], "client_id": "market", "exp": 9999999999},
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.consume",
        lambda subject, role, permission: RateDecision(False, 9),
    )
    response = _client().get(
        "/ui/market-data/BASELINE/book",
        headers={"HX-Request": "true", "Cookie": "pytradesim_session=sess"},
    )
    assert response.status_code == 429
    assert "Limit reached, retrying in 9 s" in response.text
    assert 'hx-trigger="every 9s"' in response.text
    assert response.headers["retry-after"] == "9"


def test_forbidden_page_is_html(monkeypatch):
    monkeypatch.setattr(
        "secure_api.app.web.routes.load_session",
        lambda session_id: {
            "client_id": "market",
            "roles": ["market_data_client"],
            "access_token": "token",
            "csrf_token": "csrf",
            "id_token": "",
        },
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.decode_token",
        lambda token: {"roles": ["market_data_client"], "client_id": "market", "exp": 9999999999},
    )
    response = _client().get("/ui/alerts", headers={"Cookie": "pytradesim_session=sess"})
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("text/html")
    assert "Missing permission" in response.text
    assert response.text.strip().startswith("<!DOCTYPE html>")
