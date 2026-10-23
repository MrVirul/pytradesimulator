"""Every signed-in page shares a role-aware navigation bar."""

from fastapi.testclient import TestClient

from secure_api.app.main import app


def _client():
    return TestClient(app, base_url="https://testserver")


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
    monkeypatch.setattr(
        "secure_api.app.web.routes._overview",
        lambda row: {
            "permissions": [],
            "feed": {"logged_on": False, "last_message_at": None},
            "symbols": [],
            "limits": [],
        },
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.load_session",
        lambda session_id: _session(role),
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.decode_token",
        lambda token: {"roles": [role], "client_id": role, "exp": 9999999999},
    )


def test_nav_matches_the_role(monkeypatch):
    expected = {
        "market_data_client": ["/ui", "/ui/market"],
        "surveillance_analyst": ["/ui", "/ui/market", "/ui/alerts"],
        "security_admin": ["/ui", "/ui/market", "/ui/alerts", "/ui/security", "/ui/scenarios"],
    }
    client = _client()
    for role, links in expected.items():
        _open(monkeypatch, role)
        response = client.get("/ui", headers={"Cookie": "pytradesim_session=sess"})
        assert response.status_code == 200
        assert "Sign out" in response.text
        assert 'name="csrf_token"' in response.text
        for href in ("/ui/alerts", "/ui/security", "/ui/scenarios"):
            marker = 'href="{0}"'.format(href)
            assert (marker in response.text) is (href in links)
        assert 'href="/docs"' in response.text
