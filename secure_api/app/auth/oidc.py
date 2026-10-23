"""Authorization Code + PKCE. The browser never sees the access token."""

import base64
import hashlib
import secrets
from urllib.parse import urlencode

import httpx

from secure_api.app.config import (
    keycloak_client_id,
    keycloak_internal_url,
    keycloak_realm,
    keycloak_redirect_uri,
    public_keycloak_url,
)


def public_issuer():
    return "{0}/realms/{1}".format(public_keycloak_url(), keycloak_realm())


def token_endpoint():
    base = keycloak_internal_url() or public_keycloak_url()
    return "{0}/realms/{1}/protocol/openid-connect/token".format(base, keycloak_realm())


def client_id():
    return keycloak_client_id()


def redirect_uri():
    return keycloak_redirect_uri()


def new_verifier():
    return secrets.token_urlsafe(48)


def code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def authorize_url(state, verifier, username=""):
    challenge = code_challenge(verifier)
    hint = ""
    if username:
        hint = "&login_hint={0}".format(username)
    return (
        "{0}/protocol/openid-connect/auth?response_type=code"
        "&client_id={1}&redirect_uri={2}&scope=openid"
        "&state={3}&code_challenge={4}&code_challenge_method=S256"
        "&prompt=login{5}"
    ).format(public_issuer(), client_id(), redirect_uri(), state, challenge, hint)


def logout_url(redirect_uri, state, id_token=""):
    """End the Keycloak session, then return to the app with state intact."""
    params = {
        "client_id": client_id(),
        "post_logout_redirect_uri": redirect_uri,
        "state": state,
    }
    if id_token:
        params["id_token_hint"] = id_token
    return public_issuer() + "/protocol/openid-connect/logout?" + urlencode(params)


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
    body = response.json()
    token = body.get("access_token")
    if not token:
        raise RuntimeError("token exchange failed")
    return {"access_token": token, "id_token": body.get("id_token") or ""}
