"""Security headers on API, UI, and docs responses."""

from fastapi.testclient import TestClient

from secure_api.app.main import app


def test_api_health_has_hardening_headers(monkeypatch):
    monkeypatch.setenv("PUBLIC_KEYCLOAK_URL", "http://localhost:8081")
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert "content-security-policy" not in response.headers


def test_ui_login_has_csp_without_no_store(monkeypatch):
    monkeypatch.setenv("PUBLIC_KEYCLOAK_URL", "http://keycloak.test:8081")
    client = TestClient(app)
    response = client.get("/ui/login")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers.get("cache-control") != "no-store"
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "form-action 'self' http://keycloak.test:8081" in csp
    assert "script-src 'self' 'unsafe-eval'" in csp


def test_docs_has_no_csp(monkeypatch):
    monkeypatch.setenv("PUBLIC_KEYCLOAK_URL", "http://localhost:8081")
    client = TestClient(app)
    response = client.get("/docs")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" not in response.headers
