"""Session rows. The access token stays in Postgres."""

import json
import secrets
from datetime import datetime, timedelta, timezone

from secure_api.app.config import session_minutes
from secure_api.app.db import connection, lock

SESSION_COOKIE = "pytradesim_session"
DEMO_USERS = ("market", "analyst", "admin")


def session_deadline(claims):
    """End the browser session when the access token expires, or sooner."""
    limit = datetime.now(timezone.utc) + timedelta(minutes=session_minutes())
    exp = claims.get("exp") if claims else None
    if not exp:
        return limit
    token_end = datetime.fromtimestamp(int(exp), tz=timezone.utc)
    if token_end < limit:
        return token_end
    return limit


def new_attempt():
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM oidc_attempts WHERE created_at < now() - interval '10 minutes'"
                )
                cursor.execute(
                    "INSERT INTO oidc_attempts (state, code_verifier) VALUES (%s, %s)",
                    (state, verifier),
                )
    return state, verifier


def take_attempt(state):
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT code_verifier FROM oidc_attempts WHERE state = %s",
                    (state,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                cursor.execute("DELETE FROM oidc_attempts WHERE state = %s", (state,))
    return row[0]


def save_session(claims, access_token, id_token=""):
    session_id = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    expires = session_deadline(claims)
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO browser_sessions (
                        id, client_id, subject, roles, access_token,
                        id_token, csrf_token, expires_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        claims["client_id"],
                        claims["sub"],
                        json.dumps(list(claims.get("roles") or [])),
                        access_token,
                        id_token or "",
                        csrf_token,
                        expires,
                    ),
                )
    return session_id, csrf_token


def load_session(session_id):
    if not session_id:
        return None
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT client_id, subject, roles, access_token, csrf_token,
                           expires_at, id_token
                    FROM browser_sessions
                    WHERE id = %s AND expires_at > now()
                    """,
                    (session_id,),
                )
                row = cursor.fetchone()
    if row is None:
        return None
    roles = row[2]
    if isinstance(roles, str):
        roles = json.loads(roles)
    return {
        "client_id": row[0],
        "subject": row[1],
        "roles": roles,
        "access_token": row[3],
        "csrf_token": row[4],
        "expires_at": row[5],
        "id_token": row[6] or "",
    }


def delete_session(session_id):
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM browser_sessions WHERE id = %s", (session_id,)
                )
