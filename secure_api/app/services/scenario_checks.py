"""Unauthorized-access and rate-limit scenarios.

These calls stay inside the API process. They do not send an order.
Each denied call uses one request id, and the audit row stores that same id.
"""

import os
import uuid

import httpx

from secure_api.app.auth.jwt import decode_token
from secure_api.app.auth.oidc import token_endpoint
from secure_api.app.auth.policies import allows
from secure_api.app.db import connection, lock
from secure_api.harness.scenarios import ACCESS_SCENARIOS, ScenarioError


class CheckFailed(Exception):
    def __init__(self, reason):
        super(CheckFailed, self).__init__(reason)
        self.reason = reason


def client_credentials_token():
    from secure_api.app.config import scenario_client_id, scenario_client_secret

    client_id = scenario_client_id()
    secret = scenario_client_secret()
    if not client_id or not secret:
        raise CheckFailed("unavailable")
    try:
        response = httpx.post(
            token_endpoint(),
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": secret,
            },
            timeout=10.0,
        )
    except httpx.HTTPError:
        raise CheckFailed("unavailable")
    if response.status_code != 200:
        raise CheckFailed("unavailable")
    token = response.json().get("access_token") or ""
    if not token:
        raise CheckFailed("unavailable")
    return token


def _request_id(prefix):
    return "req-{0}-{1}".format(prefix, uuid.uuid4().hex[:12])


def _call(send, token, path, request_id):
    headers = {
        "Authorization": "Bearer {0}".format(token),
        "X-Request-ID": request_id,
    }
    if send is not None:
        return send(path, headers)
    response = httpx.get(
        "http://127.0.0.1:8080{0}".format(path), headers=headers, timeout=10.0
    )
    return response


def _tighten(subject):
    """One market-data request is allowed for this subject. The next is denied."""
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO rate_limit_policies (
                        subject, category, requests_allowed, window_seconds
                    )
                    VALUES (%s, 'market_data', 1, 60)
                    ON CONFLICT (subject, category) DO UPDATE
                    SET requests_allowed = 1, window_seconds = 60
                    """,
                    (subject,),
                )
                cursor.execute(
                    """
                    UPDATE rate_limit_counters
                    SET request_count = 0, window_start = now()
                    WHERE subject = %s AND category = 'market_data'
                    """,
                    (subject,),
                )


def _audit_status(request_id):
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT status_code
                    FROM audit_events
                    WHERE request_id = %s
                    """,
                    (request_id,),
                )
                row = cursor.fetchone()
    if row is None:
        return None
    return row[0]


def run_access_scenario(name, send=None, token=None):
    if name not in ACCESS_SCENARIOS:
        raise ScenarioError("unknown_scenario")
    bearer = token or client_credentials_token()
    claims = decode_token(bearer)
    if "market_data_client" not in claims.get("roles", []):
        raise CheckFailed("unavailable")
    if allows(claims.get("roles"), "audit:read"):
        raise CheckFailed("unavailable")
    subject = claims["client_id"]
    previous = os.environ.get("RATE_LIMIT_REQUIRED")
    os.environ["RATE_LIMIT_REQUIRED"] = "1"
    try:
        if name == "unauthorized_access":
            request_id = _request_id("unauth")
            response = _call(send, bearer, "/api/v1/audit-events", request_id)
            if response.status_code != 403:
                raise CheckFailed("expected_forbidden")
            expected = 403
        else:
            _tighten(subject)
            warmup = _request_id("limitok")
            first = _call(send, bearer, "/api/v1/market-data", warmup)
            if first.status_code != 200:
                raise CheckFailed("expected_allowed")
            request_id = _request_id("limit")
            response = _call(send, bearer, "/api/v1/market-data", request_id)
            if response.status_code != 429:
                raise CheckFailed("expected_limited")
            expected = 429
    finally:
        if previous is None:
            os.environ.pop("RATE_LIMIT_REQUIRED", None)
        else:
            os.environ["RATE_LIMIT_REQUIRED"] = previous
    if _audit_status(request_id) != expected:
        raise CheckFailed("missing_audit")
    return {"status": "passed", "detail": request_id}
