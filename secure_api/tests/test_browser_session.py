"""Browser login keeps the access token out of the page and out of script storage."""

import os
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from secure_api.app.auth.oidc import code_challenge
from secure_api.app.main import app


ISSUER = "https://issuer.test/realms/pytradesim"
AUDIENCE = "pytradesim-api"
RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


@pytest.fixture
def keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem.decode("ascii")


@pytest.fixture
def client(keys, monkeypatch):
    _private, public = keys
    monkeypatch.setenv("JWT_PUBLIC_KEY", public)
    monkeypatch.setenv("JWT_ISSUER", ISSUER)
    monkeypatch.setenv("JWT_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("RATE_LIMIT_REQUIRED", "0")
    return TestClient(app, base_url="https://testserver")


def _token(private_pem, roles, **overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "demo-market-client",
        "client_id": "demo-market-client",
        "roles": roles,
        "iat": now,
        "exp": now + 60,
    }
    claims.update(overrides)
    return jwt.encode(claims, private_pem, algorithm="RS256")


def test_pkce_matches_the_rfc_vector():
    assert code_challenge(RFC_VERIFIER) == RFC_CHALLENGE


def test_login_page_does_not_store_a_token(client):
    response = client.get("/ui/login")
    assert response.status_code == 200
    text = response.text
    assert "localStorage" not in text
    assert "sessionStorage" not in text
    assert "access_token" not in text
    assert 'href="/ui/login/start?user=market"' in text


def test_login_cards_use_the_environment(client, monkeypatch):
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "changeme")
    monkeypatch.setenv("SHOW_DEMO_CREDENTIALS", "1")
    shown = client.get("/ui/login")
    assert "changeme" in shown.text
    assert "Signed out." in client.get("/ui/login", params={"state": "signed_out"}).text
    assert "Session expired" in client.get("/ui/login", params={"error": "expired"}).text
    monkeypatch.setenv("SHOW_DEMO_CREDENTIALS", "0")
    hidden = client.get("/ui/login")
    assert "changeme" not in hidden.text
    assert 'href="/ui/login/start?user=admin"' in hidden.text


def test_login_start_fails_closed_without_a_database(client):
    if os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is set")
    response = client.get("/ui/login/start")
    assert response.status_code == 503


def test_callback_cookie_hides_the_access_token(client, keys, monkeypatch):
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    private, _public = keys
    token = _token(private, ["market_data_client"])
    monkeypatch.setattr(
        "secure_api.app.web.routes.exchange_code", lambda verifier, code: token
    )
    started = client.get("/ui/login/start", follow_redirects=False)
    assert started.status_code == 302
    location = urlparse(started.headers["location"])
    params = parse_qs(location.query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"][0] == code_challenge(
        _verifier_for_state(params["state"][0])
    )
    finished = client.get(
        "/ui/callback",
        params={"code": "demo-code", "state": params["state"][0]},
        follow_redirects=False,
    )
    assert finished.status_code == 303
    cookie = finished.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" in cookie
    assert token not in finished.text
    assert token not in finished.headers.get("set-cookie", "")
    home = client.get("/ui")
    assert home.status_code == 200
    assert "demo-market-client" in home.text
    assert token not in home.text
    assert "localStorage" not in home.text
    denied = client.post("/ui/logout", data={"csrf_token": "nope"}, follow_redirects=False)
    assert denied.status_code == 403


def test_login_start_asks_for_the_named_user(client, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("PUBLIC_API_URL", "http://localhost:8080")
    monkeypatch.setattr(
        "secure_api.app.web.routes.new_attempt", lambda: ("state-1", "verifier-1")
    )
    monkeypatch.setattr("secure_api.app.web.routes.load_session", lambda session_id: None)
    response = client.get("/ui/login/start", params={"user": "market"}, follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    assert "login_hint=market" in location
    assert "prompt=login" in location
    monkeypatch.setattr(
        "secure_api.app.web.routes.load_session",
        lambda session_id: {"id_token": "id-token-value", "client_id": "admin"},
    )
    monkeypatch.setattr("secure_api.app.web.routes.delete_session", lambda session_id: None)
    switching = client.get(
        "/ui/login/start",
        params={"user": "market"},
        headers={"Cookie": "pytradesim_session=sess"},
        follow_redirects=False,
    )
    assert "/protocol/openid-connect/logout" in switching.headers["location"]
    assert "id_token_hint=id-token-value" in switching.headers["location"]
    resumed = client.get("/ui/login/resume", params={"state": "market"}, follow_redirects=False)
    assert resumed.status_code == 302
    resumed_location = resumed.headers["location"]
    assert "login_hint=market" in resumed_location
    assert "prompt=login" in resumed_location
    unknown = client.get("/ui/login/start", params={"user": "other"}, follow_redirects=False)
    assert unknown.status_code == 302
    assert unknown.headers["location"].endswith("/ui/login?error=unknown_user")


def test_used_sign_in_returns_to_the_login_page(client, monkeypatch):
    monkeypatch.setattr("secure_api.app.web.routes.take_attempt", lambda state: None)
    response = client.get(
        "/ui/callback",
        params={"code": "used", "state": "gone"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"].endswith("/ui/login?error=expired")


def test_session_ends_when_the_token_expires(monkeypatch):
    monkeypatch.setenv("SESSION_MINUTES", "15")
    from secure_api.app.auth.browser import session_deadline

    soon = int(time.time()) + 30
    deadline = session_deadline({"exp": soon})
    assert int(deadline.timestamp()) <= soon + 1


def _verifier_for_state(state):
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT code_verifier FROM oidc_attempts WHERE state = %s", (state,)
            )
            return cursor.fetchone()[0]
