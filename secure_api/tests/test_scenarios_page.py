"""An admin can start a named scenario. Other roles cannot open the lab."""

import os
import re
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


def _token(private_pem, roles, client_id):
    now = int(time.time())
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": client_id,
            "client_id": client_id,
            "roles": roles,
            "iat": now,
            "exp": now + 60,
        },
        private_pem,
        algorithm="RS256",
    )


def _sign_in(client, monkeypatch, private_pem, roles, client_id):
    token = _token(private_pem, roles, client_id)
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


def _csrf(page):
    found = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert found is not None
    return found.group(1)


def test_scenarios_require_a_session(client):
    response = client.get("/ui/scenarios", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/ui/login?error=expired"


def test_market_client_cannot_open_the_lab(client, keys, monkeypatch):
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    private, _public = keys
    _sign_in(client, monkeypatch, private, ["market_data_client"], "demo-market-lab")
    home = client.get("/ui")
    assert 'href="/ui/scenarios"' not in home.text
    page = client.get("/ui/scenarios")
    assert page.status_code == 403
    assert page.json()["error"]["code"] == "forbidden"


def test_analyst_cannot_open_the_lab(client, keys, monkeypatch):
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    private, _public = keys
    _sign_in(client, monkeypatch, private, ["surveillance_analyst"], "demo-analyst-lab")
    page = client.get("/ui/scenarios")
    assert page.status_code == 403


def test_admin_runs_a_named_scenario_without_an_order_field(client, keys, monkeypatch):
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    private, _public = keys
    token = _sign_in(client, monkeypatch, private, ["security_admin"], "demo-admin-lab")
    home = client.get("/ui")
    assert 'href="/ui/scenarios"' in home.text
    page = client.get("/ui/scenarios")
    assert page.status_code == 200
    for name in (
        "price_movement",
        "spread_widening",
        "volume",
        "unauthorized_access",
        "rate_limit_abuse",
    ):
        assert name in page.text
    assert "requests per" in page.text
    assert 'name="price"' not in page.text
    assert 'name="quantity"' not in page.text
    assert 'name="symbol"' not in page.text
    assert 'name="side"' not in page.text
    assert "localStorage" not in page.text
    assert token not in page.text
    csrf = _csrf(page)
    rejected = client.post(
        "/ui/scenarios",
        data={"csrf_token": csrf, "scenario": "spread_widening", "price": "1"},
    )
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "free_form_order"
    missing = client.post(
        "/ui/scenarios",
        data={"scenario": "spread_widening"},
    )
    assert missing.status_code == 403
    started = client.post(
        "/ui/scenarios",
        data={"csrf_token": csrf, "scenario": "spread_widening"},
        follow_redirects=False,
    )
    assert started.status_code == 303
    location = started.headers["location"]
    assert location.startswith("/ui/scenarios?run=")
    follow = client.get(location)
    assert follow.status_code == 200
    assert "pending" in follow.text or "running" in follow.text
    extra = client.post(
        "/api/v1/scenarios",
        json={"scenario": "volume", "quantity": 5},
        headers={"Authorization": "Bearer {0}".format(token)},
    )
    assert extra.status_code == 400
    assert extra.json()["error"]["code"] == "free_form_order"
    queued = client.post(
        "/api/v1/scenarios",
        json={"scenario": "volume"},
        headers={"Authorization": "Bearer {0}".format(token)},
    )
    assert queued.status_code == 200
    body = queued.json()["run"]
    assert body["scenario"] == "volume"
    assert body["symbol"] == "VOLUME"
    assert body["status"] == "pending"
    assert token not in queued.text
