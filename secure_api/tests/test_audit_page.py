"""A security admin can find a 403 or 429 by request id."""

import os
import time
import uuid
from urllib.parse import parse_qs, urlparse

import jwt
import psycopg
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


def test_audit_requires_a_session(client):
    response = client.get("/ui/audit", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/ui/login?error=expired"


def test_denied_calls_can_be_found_by_request_id(client, keys, monkeypatch):
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    private, _public = keys
    subject = "audit-{0}".format(uuid.uuid4().hex[:12])
    forbidden_id = "req-403-{0}".format(uuid.uuid4().hex[:8])
    limited_id = "req-429-{0}".format(uuid.uuid4().hex[:8])
    market = _sign_in(
        client, monkeypatch, private, ["market_data_client"], subject
    )
    hidden = client.get("/ui/audit")
    assert hidden.status_code == 403
    forbidden = client.get("/ui/alerts", headers={"X-Request-ID": forbidden_id})
    assert forbidden.status_code == 403
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO rate_limit_policies (
                    subject, category, requests_allowed, window_seconds
                )
                VALUES (%s, 'market_data', 1, 60)
                ON CONFLICT (subject, category) DO UPDATE
                SET requests_allowed = 1
                """,
                (subject,),
            )
    monkeypatch.setenv("RATE_LIMIT_REQUIRED", "1")
    assert client.get("/ui/market").status_code == 200
    limited = client.get("/ui/market", headers={"X-Request-ID": limited_id})
    assert limited.status_code == 429
    admin = _sign_in(
        client, monkeypatch, private, ["security_admin"], "demo-security-admin"
    )
    page = client.get("/ui/audit", params={"request_id": forbidden_id})
    assert page.status_code == 200
    assert forbidden_id in page.text
    assert ">403<" in page.text
    assert market not in page.text
    assert "localStorage" not in page.text
    limited_page = client.get("/ui/audit/rows", params={"request_id": limited_id})
    assert limited_page.status_code == 200
    assert limited_id in limited_page.text
    assert ">429<" in limited_page.text
    api = client.get(
        "/api/v1/audit-events",
        params={"request_id": forbidden_id, "status_code": "403"},
        headers={"Authorization": "Bearer {0}".format(admin)},
    )
    assert api.status_code == 200
    matches = [
        event
        for event in api.json()["events"]
        if event["request_id"] == forbidden_id and event["status_code"] == 403
    ]
    assert matches
    assert admin not in api.text
    rejected = client.get("/ui/audit", params={"status_code": "99"})
    assert rejected.status_code == 400
