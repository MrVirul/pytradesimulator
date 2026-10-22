"""Analysts can filter alerts. A market-data client cannot open the page."""

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


def _insert_alert(symbol):
    name = "rule-{0}".format(uuid.uuid4().hex[:12])
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO surveillance_rules (name, threshold)
                VALUES (%s, 10)
                RETURNING id
                """,
                (name,),
            )
            rule_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO surveillance_alerts (
                    rule_id, symbol, severity, observed_value, threshold, detail
                )
                VALUES (%s, %s, 'warning', 12.5, 10, 'observed value crossed the threshold')
                """,
                (rule_id, symbol),
            )
    return name


def test_alerts_require_a_session(client):
    response = client.get("/ui/alerts", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/ui/login"


def test_market_client_cannot_open_alerts(client, keys, monkeypatch):
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    private, _public = keys
    token = _sign_in(
        client, monkeypatch, private, ["market_data_client"], "demo-market-client"
    )
    home = client.get("/ui")
    assert 'href="/ui/alerts"' not in home.text
    page = client.get("/ui/alerts")
    assert page.status_code == 403
    assert page.json()["error"]["code"] == "forbidden"
    api = client.get(
        "/api/v1/alerts", headers={"Authorization": "Bearer {0}".format(token)}
    )
    assert api.status_code == 403
    assert token not in page.text


def test_analyst_can_filter_alerts(client, keys, monkeypatch):
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    private, _public = keys
    token = _sign_in(
        client, monkeypatch, private, ["surveillance_analyst"], "demo-analyst"
    )
    kept = "QALERT{0}".format(uuid.uuid4().hex[:6].upper())
    other = "QALERT{0}".format(uuid.uuid4().hex[:6].upper())
    rule_name = _insert_alert(kept)
    _insert_alert(other)
    page = client.get("/ui/alerts", params={"symbol": kept})
    assert page.status_code == 200
    assert kept in page.text
    assert other not in page.text
    assert "12.5" in page.text
    assert "observed value crossed the threshold" in page.text
    assert "localStorage" not in page.text
    assert token not in page.text
    rows = client.get("/ui/alerts/rows", params={"symbol": kept, "severity": "warning"})
    assert rows.status_code == 200
    assert kept in rows.text
    assert other not in rows.text
    api = client.get(
        "/api/v1/alerts",
        params={"symbol": kept, "rule_name": rule_name},
        headers={"Authorization": "Bearer {0}".format(token)},
    )
    assert api.status_code == 200
    body = api.json()["alerts"]
    assert len(body) == 1
    assert body[0]["symbol"] == kept
    assert body[0]["observed_value"] == 12.5
    assert body[0]["threshold"] == 10.0
    rejected = client.get("/ui/alerts", params={"symbol": "nope!"})
    assert rejected.status_code == 400
