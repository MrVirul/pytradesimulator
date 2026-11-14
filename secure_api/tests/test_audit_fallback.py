"""A failed audit write leaves a stderr JSON line, not a silent drop."""

import json
import time

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
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused/for/audit/fallback")
    return TestClient(app)


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


def test_failed_audit_write_prints_stderr_json(client, keys, monkeypatch, capsys):
    private, _public = keys
    token = _token(private, ["market_data_client"])
    monkeypatch.setattr("secure_api.app.main.list_symbols", lambda: [])

    def boom(_event):
        raise RuntimeError("store down")

    monkeypatch.setattr("secure_api.app.main.write_event", boom)
    response = client.get(
        "/api/v1/market-data",
        headers={
            "Authorization": "Bearer {0}".format(token),
            "X-Request-ID": "req-audit-fallback",
        },
    )
    assert response.status_code == 200
    err = capsys.readouterr().err.strip().splitlines()
    assert err
    payload = json.loads(err[-1])
    assert payload["audit_write_failed"] is True
    assert payload["request_id"] == "req-audit-fallback"
    assert payload["client_id"] == "demo-market-client"
    assert payload["action"] == "market-data:read"
    assert payload["decision"] == "allowed"
    assert payload["status_code"] == 200
    assert "latency_ms" in payload
    assert token not in err[-1]
    assert "Bearer" not in err[-1]
