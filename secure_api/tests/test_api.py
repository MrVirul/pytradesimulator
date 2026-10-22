import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from secure_api.app.main import app


ISSUER = "https://issuer.test/realms/pytradesim"
AUDIENCE = "pytradesim-api"


@pytest.fixture(scope="module")
def keys(monkeypatch_module):
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


@pytest.fixture(scope="module")
def monkeypatch_module():
    patcher = pytest.MonkeyPatch()
    yield patcher
    patcher.undo()


@pytest.fixture(scope="module")
def client(keys, monkeypatch_module):
    _private, public = keys
    monkeypatch_module.setenv("JWT_PUBLIC_KEY", public)
    monkeypatch_module.setenv("JWT_ISSUER", ISSUER)
    monkeypatch_module.setenv("JWT_AUDIENCE", AUDIENCE)
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


def test_health_is_public(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.parametrize(
    "header,reason_status",
    [
        (None, 401),
        ("Bearer not-a-token", 401),
    ],
)
def test_missing_and_malformed_tokens_are_rejected(client, header, reason_status):
    headers = {} if header is None else {"Authorization": header}
    response = client.get("/api/v1/market-data", headers=headers)
    assert response.status_code == reason_status
    assert response.json()["error"]["code"] == "unauthorized"


def test_expired_token_is_rejected(client, keys):
    private, _public = keys
    token = _token(private, ["market_data_client"], exp=int(time.time()) - 10)
    response = client.get(
        "/api/v1/market-data", headers={"Authorization": "Bearer {0}".format(token)}
    )
    assert response.status_code == 401


def test_wrong_audience_is_rejected(client, keys):
    private, _public = keys
    token = _token(private, ["market_data_client"], aud="someone-else")
    response = client.get(
        "/api/v1/market-data", headers={"Authorization": "Bearer {0}".format(token)}
    )
    assert response.status_code == 401


def test_valid_market_data_token_is_accepted(client, keys):
    private, _public = keys
    token = _token(private, ["market_data_client"])
    response = client.get(
        "/api/v1/market-data", headers={"Authorization": "Bearer {0}".format(token)}
    )
    assert response.status_code == 200


def test_market_data_token_cannot_read_audit(client, keys):
    private, _public = keys
    token = _token(private, ["market_data_client"])
    response = client.get(
        "/api/v1/audit-events", headers={"Authorization": "Bearer {0}".format(token)}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
