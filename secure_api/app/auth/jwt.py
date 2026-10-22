"""Validate access tokens. The token itself is never returned or logged."""

import os

import jwt
from jwt import PyJWKClient

from secure_api.app.auth.policies import ROLE_PERMISSIONS
from secure_api.app.config import jwt_audience, jwt_issuer


class TokenError(Exception):
    def __init__(self, reason):
        super(TokenError, self).__init__(reason)
        self.reason = reason


def _signing_key(token):
    key = os.environ.get("JWT_PUBLIC_KEY", "").replace("\\n", "\n")
    if key:
        return key
    url = os.environ.get("JWT_JWKS_URL", "")
    if not url:
        raise TokenError("malformed")
    try:
        return PyJWKClient(url).get_signing_key_from_jwt(token).key
    except Exception:
        raise TokenError("malformed")


def decode_token(token):
    if not token:
        raise TokenError("missing_token")
    try:
        claims = jwt.decode(
            token,
            _signing_key(token),
            algorithms=["RS256"],
            audience=jwt_audience(),
            issuer=jwt_issuer(),
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except TokenError:
        raise
    except jwt.ExpiredSignatureError:
        raise TokenError("expired")
    except jwt.InvalidAudienceError:
        raise TokenError("invalid_audience")
    except jwt.InvalidIssuerError:
        raise TokenError("invalid_issuer")
    except jwt.InvalidTokenError:
        raise TokenError("malformed")
    roles = claims.get("roles") or []
    if not roles:
        realm = claims.get("realm_access") or {}
        roles = realm.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    claims["roles"] = [role for role in roles if role in ROLE_PERMISSIONS]
    if "client_id" not in claims:
        claims["client_id"] = claims.get("preferred_username") or claims["sub"]
    return claims
