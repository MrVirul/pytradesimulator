"""Append-only audit writes. Callers must not pass tokens or cookies."""

import re
from datetime import datetime, timedelta, timezone

from secure_api.app.db import connection, lock

_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_ACTION = re.compile(r"^[a-z0-9:._-]{1,64}$")
_DECISIONS = ("allowed", "denied")


def write_event(event):
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO audit_events (
                        request_id, client_id, action, resource,
                        decision, reason, status_code, latency_ms
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event["request_id"],
                        event["client_id"],
                        event["action"],
                        event["resource"],
                        event["decision"],
                        event["reason"],
                        event["status_code"],
                        event["latency_ms"],
                    ),
                )


def _parse_time(value):
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    if len(text) == 16:
        text = text + ":00+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def search_error(request_id, client_id, action, decision, status_code, recorded_from, recorded_to):
    if request_id and _TOKEN.match(request_id) is None:
        return "invalid_request_id"
    if client_id and _TOKEN.match(client_id) is None:
        return "invalid_client_id"
    if action and _ACTION.match(action) is None:
        return "invalid_action"
    if decision and decision not in _DECISIONS:
        return "invalid_decision"
    if status_code not in ("", None):
        if not str(status_code).isdigit() or not 100 <= int(status_code) <= 599:
            return "invalid_status"
    for value in (recorded_from, recorded_to):
        if not value:
            continue
        try:
            _parse_time(value)
        except ValueError:
            return "invalid_time"
    return None


def list_events(
    request_id=None,
    client_id="",
    action="",
    decision="",
    status_code=None,
    recorded_from="",
    recorded_to="",
):
    clauses = []
    params = []
    if request_id:
        clauses.append("request_id = %s")
        params.append(request_id)
    if client_id:
        clauses.append("client_id = %s")
        params.append(client_id)
    if action:
        clauses.append("action = %s")
        params.append(action)
    if decision:
        clauses.append("decision = %s")
        params.append(decision)
    if status_code not in ("", None):
        clauses.append("status_code = %s")
        params.append(int(status_code))
    start = _parse_time(recorded_from)
    end = _parse_time(recorded_to)
    if start is not None:
        clauses.append("recorded_at >= %s")
        params.append(start)
    if end is not None:
        clauses.append("recorded_at <= %s")
        params.append(end)
    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(clauses)
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT request_id, client_id, action, resource,
                           decision, reason, status_code, latency_ms, recorded_at
                    FROM audit_events
                    {0}
                    ORDER BY id DESC
                    LIMIT 50
                    """.format(where),
                    params,
                )
                rows = cursor.fetchall()
    return [
        {
            "request_id": row[0],
            "client_id": row[1],
            "action": row[2],
            "resource": row[3],
            "decision": row[4],
            "reason": row[5],
            "status_code": row[6],
            "latency_ms": row[7],
            "recorded_at": row[8].isoformat(),
        }
        for row in rows
    ]


def _number(value):
    if value is None:
        return None
    return float(value)


def security_metrics(minutes):
    window = 60 if int(minutes) == 60 else 15
    since = datetime.now(timezone.utc) - timedelta(minutes=window)
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT count(*),
                           count(*) FILTER (WHERE decision = 'allowed'),
                           count(*) FILTER (WHERE decision = 'denied'),
                           count(*) FILTER (WHERE status_code = 401),
                           count(*) FILTER (WHERE status_code = 403),
                           count(*) FILTER (WHERE status_code = 429),
                           percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms),
                           percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms),
                           percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_ms)
                    FROM audit_events
                    WHERE recorded_at >= %s
                    """,
                    (since,),
                )
                totals = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT date_trunc('minute', recorded_at), count(*)
                    FROM audit_events
                    WHERE recorded_at >= %s
                    GROUP BY 1
                    ORDER BY 1
                    """,
                    (since,),
                )
                minutes_rows = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT client_id, count(*)
                    FROM audit_events
                    WHERE recorded_at >= %s
                    GROUP BY client_id
                    ORDER BY count(*) DESC
                    LIMIT 5
                    """,
                    (since,),
                )
                clients = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT p.subject, p.category, p.requests_allowed,
                           c.request_count, c.window_start, p.window_seconds
                    FROM rate_limit_policies AS p
                    LEFT JOIN rate_limit_counters AS c
                      ON c.subject = p.subject AND c.category = p.category
                    ORDER BY p.category, p.subject
                    """
                )
                policies = cursor.fetchall()
    peak = max([row[1] for row in minutes_rows] or [1])
    return {
        "minutes": window,
        "requests": int(totals[0]),
        "allowed": int(totals[1]),
        "denied": int(totals[2]),
        "status_401": int(totals[3]),
        "status_403": int(totals[4]),
        "status_429": int(totals[5]),
        "p50": _number(totals[6]),
        "p95": _number(totals[7]),
        "p99": _number(totals[8]),
        "per_minute": [
            {
                "minute": row[0].isoformat(),
                "count": int(row[1]),
                "width": int(row[1] * 100 / peak),
            }
            for row in minutes_rows
        ],
        "clients": [{"client_id": row[0], "count": int(row[1])} for row in clients],
        "policies": [
            {
                "subject": row[0],
                "category": row[1],
                "allowed": int(row[2]),
                "used": 0 if row[3] is None else int(row[3]),
                "window_seconds": int(row[5]),
            }
            for row in policies
        ],
    }
