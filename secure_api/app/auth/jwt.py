"""Validate access tokens. The token itself is never returned or logged."""

import jwt

from secure_api.app.config import jwt_audience, jwt_issuer, jwt_public_key


class TokenError(Exception):
    def __init__(self, reason):
        super(TokenError, self).__init__(reason)
        self.reason = reason


def decode_token(token):
    if not token:
        raise TokenError("missing_token")
    try:
        claims = jwt.decode(
            token,
            jwt_public_key(),
            algorithms=["RS256"],
            audience=jwt_audience(),
            issuer=jwt_issuer(),
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise TokenError("expired")
    except jwt.InvalidAudienceError:
        raise TokenError("invalid_audience")
    except jwt.InvalidIssuerError:
        raise TokenError("invalid_issuer")
    except jwt.InvalidTokenError:
        raise TokenError("malformed")
    roles = claims.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    claims["roles"] = roles
    if "client_id" not in claims:
        claims["client_id"] = claims["sub"]
    return claims
