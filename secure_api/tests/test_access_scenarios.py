"""Denied scenario calls are stored on the audit row for that request id."""

import os
import re
import time
import uuid
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from secure_api.app.main import app
from secure_api.app.services.audit import list_events
from secure_api.app.services.scenario_checks import run_access_scenario


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


def _send(client, token):
    def send(path, headers):
        return client.get(path, headers=headers)

    return send


def _events(request_id, token):
    found = list_events(request_id)
    assert found
    assert found[0]["request_id"] == request_id
    assert token not in str(found)
    return found[0]


def test_both_denials_are_stored_under_their_request_ids(client, keys):
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    private, _public = keys
    subject = "lab{0}".format(uuid.uuid4().hex[:12])
    token = _token(private, ["market_data_client"], subject)
    send = _send(client, token)
    forbidden = run_access_scenario(
        "unauthorized_access", send=send, token=token
    )
    limited = run_access_scenario("rate_limit_abuse", send=send, token=token)
    assert forbidden["detail"] != limited["detail"]
    denied = _events(forbidden["detail"], token)
    assert denied["status_code"] == 403
    assert denied["decision"] == "denied"
    assert denied["action"] == "audit:read"
    blocked = _events(limited["detail"], token)
    assert blocked["status_code"] == 429
    assert blocked["decision"] == "denied"
    assert blocked["reason"] == "rate_limited"


def _sign_in(client, monkeypatch, private_pem):
    token = _token(private_pem, ["security_admin"], "demo-admin-access")
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


def test_lab_links_the_audit_request_id(client, keys, monkeypatch):
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    private, _public = keys
    token = _sign_in(client, monkeypatch, private)

    def fake(name, send=None, token=None):
        return {"status": "passed", "detail": "req-unauth-page"}

    monkeypatch.setattr(
        "secure_api.app.services.scenarios.run_access_scenario", fake
    )
    page = client.get("/ui/scenarios")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    started = client.post(
        "/ui/scenarios",
        data={"csrf_token": csrf, "scenario": "unauthorized_access"},
        follow_redirects=False,
    )
    assert started.status_code == 303
    shown = client.get(started.headers["location"])
    assert shown.status_code == 200
    assert "req-unauth-page" in shown.text
    assert 'href="/ui/audit?request_id=req-unauth-page"' in shown.text
    assert "does not send an order" in shown.text
    assert token not in shown.text
