"""JWKS client is constructed once per URL, not on every decode."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from secure_api.app.auth import jwt as jwt_mod


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


def _token(private_pem, **overrides):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "jwks-client",
        "client_id": "jwks-client",
        "roles": ["market_data_client"],
        "iat": now,
        "exp": now + 60,
    }
    claims.update(overrides)
    return jwt.encode(claims, private_pem, algorithm="RS256")


def test_jwks_client_is_constructed_once_per_url(monkeypatch, keys):
    private_pem, public_pem = keys
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("JWT_JWKS_URL", "https://issuer.test/jwks")
    monkeypatch.setenv("JWT_ISSUER", ISSUER)
    monkeypatch.setenv("JWT_AUDIENCE", AUDIENCE)
    jwt_mod._jwks_clients.clear()

    constructed = []

    class FakeKey(object):
        def __init__(self):
            self.key = public_pem

    class FakeClient(object):
        def __init__(self, url, cache_keys=True, lifespan=300):
            constructed.append((url, cache_keys, lifespan))
            self.url = url

        def get_signing_key_from_jwt(self, token):
            return FakeKey()

    monkeypatch.setattr(jwt_mod, "PyJWKClient", FakeClient)
    token = _token(private_pem)
    jwt_mod.decode_token(token)
    jwt_mod.decode_token(token)
    assert len(constructed) == 1
    assert constructed[0] == ("https://issuer.test/jwks", True, 300)
