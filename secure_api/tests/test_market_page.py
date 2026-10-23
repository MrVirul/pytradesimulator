"""The market fragment shows the stored book, its age, and its status."""

import os
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from secure_api.app.main import app


ISSUER = "https://issuer.test/realms/pytradesim"
AUDIENCE = "pytradesim-api"


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


def _token(private_pem, roles):
    now = int(time.time())
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "demo-market-client",
            "client_id": "demo-market-client",
            "roles": roles,
            "iat": now,
            "exp": now + 60,
        },
        private_pem,
        algorithm="RS256",
    )


def _sign_in(client, monkeypatch, private_pem):
    token = _token(private_pem, ["market_data_client"])
    monkeypatch.setattr(
        "secure_api.app.web.routes.exchange_code", lambda verifier, code: token
    )
    started = client.get("/ui/login/start", follow_redirects=False)
    state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
    finished = client.get(
        "/ui/callback",
        params={"code": "demo-code", "state": state},
        follow_redirects=False,
    )
    assert finished.status_code == 303
    return token


def test_market_page_requires_a_session(client):
    response = client.get("/ui/market", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/ui/login?error=expired"


def test_book_fragment_shows_age_and_status(client, keys, monkeypatch):
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    private, _public = keys
    token = _sign_in(client, monkeypatch, private)
    page = client.get("/ui/market")
    assert page.status_code == 200
    assert 'id="market-book"' in page.text
    assert 'hx-get="/ui/market-data/BASELINE/book"' in page.text
    assert "visibilityState" in page.text
    assert "localStorage" not in page.text
    assert token not in page.text
    fragment = client.get("/ui/market-data/BASELINE/book")
    assert fragment.status_code == 200
    text = fragment.text
    assert "Status live" in text or "Status stale" in text
    assert "Age" in text
    assert "s</dd>" in text
    assert "Received" in text
    assert "2026-" in text
    assert "51.0" in text
    assert token not in text
    assert "localStorage" not in text
    rejected = client.get("/ui/market", params={"symbol": "nope!"})
    assert rejected.status_code == 400
