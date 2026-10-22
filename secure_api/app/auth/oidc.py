"""Authorization Code + PKCE. The browser never sees the access token."""

import base64
import hashlib
import os
import secrets

import httpx


def public_issuer():
    base = os.environ.get("KEYCLOAK_PUBLIC_URL", "http://localhost:8081").rstrip("/")
    realm = os.environ.get("KEYCLOAK_REALM", "pytradesim")
    return "{0}/realms/{1}".format(base, realm)


def token_endpoint():
    base = os.environ.get("KEYCLOAK_INTERNAL_URL", "").rstrip("/")
    realm = os.environ.get("KEYCLOAK_REALM", "pytradesim")
    if not base:
        base = os.environ.get("KEYCLOAK_PUBLIC_URL", "http://localhost:8081").rstrip("/")
    return "{0}/realms/{1}/protocol/openid-connect/token".format(base, realm)


def client_id():
    return os.environ.get("KEYCLOAK_CLIENT_ID", "pytradesim-ui")


def redirect_uri():
    return os.environ.get(
        "KEYCLOAK_REDIRECT_URI", "http://localhost:8080/ui/callback"
    )


def new_verifier():
    return secrets.token_urlsafe(48)


def code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def authorize_url(state, verifier):
    challenge = code_challenge(verifier)
    return (
        "{0}/protocol/openid-connect/auth?response_type=code"
        "&client_id={1}&redirect_uri={2}&scope=openid"
        "&state={3}&code_challenge={4}&code_challenge_method=S256"
    ).format(public_issuer(), client_id(), redirect_uri(), state, challenge)


def exchange_code(verifier, code):
    response = httpx.post(
        token_endpoint(),
        data={
            "grant_type": "authorization_code",
            "client_id": client_id(),
            "redirect_uri": redirect_uri(),
            "code": code,
            "code_verifier": verifier,
        },
        timeout=10.0,
    )
    if response.status_code != 200:
        raise RuntimeError("token exchange failed")
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("token exchange failed")
    return token
