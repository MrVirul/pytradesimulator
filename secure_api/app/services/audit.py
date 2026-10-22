"""Append-only audit writes. Callers must not pass tokens or cookies."""

import re
from datetime import datetime, timezone

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
