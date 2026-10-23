"""Atomic Postgres rate limit. If the store cannot be used, the call is denied."""

from datetime import datetime, timedelta, timezone

from secure_api.app.auth.policies import RATE_CATEGORY, ROLE_PERMISSIONS
from secure_api.app.db import connection, lock


class RateDecision(object):
    def __init__(self, allowed, retry_after, unavailable=False):
        self.allowed = allowed
        self.retry_after = retry_after
        self.unavailable = unavailable


def category_for(permission):
    return RATE_CATEGORY.get(permission, "market_data")


def categories_for(roles):
    found = []
    for role in roles or []:
        for permission in sorted(ROLE_PERMISSIONS.get(role, ())):
            category = RATE_CATEGORY.get(permission)
            if category and category not in found:
                found.append(category)
    return found


def snapshot(subject, roles):
    """Read the caller's limit and usage. This does not consume a request."""
    try:
        with lock():
            conn = connection()
            with conn.transaction():
                return _snapshot(conn, subject, roles)
    except Exception:
        return []


def _snapshot(conn, subject, roles):
    now = datetime.now(timezone.utc)
    usage = []
    with conn.cursor() as cursor:
        for category in categories_for(roles):
            policy = _policy(cursor, subject, (roles or [""])[0], category)
            if policy is None:
                continue
            _matched, allowed, window_seconds = policy
            cursor.execute(
                """
                SELECT window_start, request_count
                FROM rate_limit_counters
                WHERE subject = %s AND category = %s
                """,
                (subject, category),
            )
            row = cursor.fetchone()
            used = 0
            resets_at = None
            if row is not None:
                window_start, request_count = row
                if window_start.tzinfo is None:
                    window_start = window_start.replace(tzinfo=timezone.utc)
                if now - window_start < timedelta(seconds=int(window_seconds)):
                    used = int(request_count)
                    resets_at = (window_start + timedelta(seconds=int(window_seconds))).isoformat()
            usage.append(
                {
                    "category": category,
                    "used": used,
                    "allowed": int(allowed),
                    "resets_at": resets_at,
                }
            )
    return usage


def consume(subject, role, permission):
    category = category_for(permission)
    try:
        with lock():
            conn = connection()
            with conn.transaction():
                return _consume(conn, subject, role, category)
    except Exception:
        return RateDecision(False, 60, unavailable=True)


def _policy(cursor, subject, role, category):
    cursor.execute(
        """
        SELECT subject, requests_allowed, window_seconds
        FROM rate_limit_policies
        WHERE category = %s AND subject IN (%s, %s, '*')
        ORDER BY CASE subject
            WHEN %s THEN 0
            WHEN %s THEN 1
            ELSE 2
        END
        LIMIT 1
        """,
        (category, subject, role or "", subject, role or ""),
    )
    return cursor.fetchone()


def _consume(conn, subject, role, category):
    now = datetime.now(timezone.utc)
    with conn.cursor() as cursor:
        policy = _policy(cursor, subject, role, category)
        if policy is None:
            return RateDecision(False, 60, unavailable=True)
        _matched, allowed, window_seconds = policy
        window = timedelta(seconds=int(window_seconds))
        cursor.execute(
            """
            SELECT window_start, request_count
            FROM rate_limit_counters
            WHERE subject = %s AND category = %s
            FOR UPDATE
            """,
            (subject, category),
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                """
                INSERT INTO rate_limit_counters (
                    subject, category, window_start, request_count
                )
                VALUES (%s, %s, %s, 1)
                """,
                (subject, category, now),
            )
            return RateDecision(True, 0)
        window_start, request_count = row
        elapsed = now - window_start
        if elapsed >= window:
            cursor.execute(
                """
                UPDATE rate_limit_counters
                SET window_start = %s, request_count = 1
                WHERE subject = %s AND category = %s
                """,
                (now, subject, category),
            )
            return RateDecision(True, 0)
        if request_count >= int(allowed):
            retry = int((window - elapsed).total_seconds()) + 1
            return RateDecision(False, max(retry, 1))
        cursor.execute(
            """
            UPDATE rate_limit_counters
            SET request_count = request_count + 1
            WHERE subject = %s AND category = %s
            """,
            (subject, category),
        )
        return RateDecision(True, 0)
