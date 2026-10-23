"""Sign-out ends the app session and the Keycloak session."""

from fastapi.testclient import TestClient

from secure_api.app.main import app


def test_logout_sends_the_browser_to_keycloak(monkeypatch):
    monkeypatch.setattr(
        "secure_api.app.web.routes.load_session",
        lambda session_id: {
            "client_id": "admin",
            "csrf_token": "csrf-1",
            "id_token": "id-token-value",
            "roles": ["security_admin"],
        },
    )
    deleted = []
    monkeypatch.setattr(
        "secure_api.app.web.routes.delete_session",
        lambda session_id: deleted.append(session_id),
    )
    client = TestClient(app, base_url="https://testserver")
    response = client.post(
        "/ui/logout",
        data={"csrf_token": "csrf-1"},
        cookies={"pytradesim_session": "sess-1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert "/protocol/openid-connect/logout" in location
    assert "id_token_hint=id-token-value" in location
    assert "post_logout_redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Fui%2Flogin" in location
    assert "state=signed_out" in location
    assert deleted == ["sess-1"]
    assert "pytradesim_session" in response.headers.get("set-cookie", "").lower()
