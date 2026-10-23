"""Read surveillance alerts. Filters are checked before the query."""

import re
from datetime import datetime, timezone

from secure_api.app.db import connection, lock
from secure_api.app.services.market_data import SYMBOL_PATTERN, get_symbol

_SEVERITY = re.compile(r"^[a-z]{3,16}$")
_RULE_NAME = re.compile(r"^[A-Za-z0-9_. -]{1,64}$")


def _parse_time(value):
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def filter_error(symbol, severity, rule_name, created_from="", created_to=""):
    if symbol and SYMBOL_PATTERN.match(symbol) is None:
        return "invalid_symbol"
    if severity and _SEVERITY.match(severity) is None:
        return "invalid_severity"
    if rule_name and _RULE_NAME.match(rule_name) is None:
        return "invalid_rule"
    for value in (created_from, created_to):
        if not value:
            continue
        try:
            _parse_time(value)
        except ValueError:
            return "invalid_time"
    return None


def list_alerts(symbol, severity, rule_name, created_from="", created_to=""):
    clauses = []
    params = []
    if symbol:
        clauses.append("a.symbol = %s")
        params.append(symbol)
    if severity:
        clauses.append("a.severity = %s")
        params.append(severity)
    if rule_name:
        clauses.append("r.name = %s")
        params.append(rule_name)
    if created_from:
        clauses.append("a.created_at >= %s")
        params.append(_parse_time(created_from))
    if created_to:
        clauses.append("a.created_at <= %s")
        params.append(_parse_time(created_to))
    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(clauses)
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.id, r.name, a.symbol, a.severity,
                           a.observed_value, a.threshold, a.created_at, a.detail
                    FROM surveillance_alerts AS a
                    JOIN surveillance_rules AS r ON r.id = a.rule_id
                    {0}
                    ORDER BY a.id DESC
                    LIMIT 100
                    """.format(where),
                    params,
                )
                rows = cursor.fetchall()
    return [
        {
            "id": row[0],
            "rule_name": row[1],
            "symbol": row[2],
            "severity": row[3],
            "observed_value": float(row[4]),
            "threshold": float(row[5]),
            "created_at": row[6].isoformat(),
            "detail": row[7],
        }
        for row in rows
    ]


def _alert_from_row(row):
    return {
        "id": row[0],
        "rule_name": row[1],
        "symbol": row[2],
        "severity": row[3],
        "observed_value": float(row[4]),
        "threshold": float(row[5]),
        "created_at": row[6].isoformat(),
        "detail": row[7],
        "ingest_sequence": row[8],
    }


def get_alert(alert_id):
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.id, r.name, a.symbol, a.severity,
                           a.observed_value, a.threshold, a.created_at, a.detail,
                           a.ingest_sequence
                    FROM surveillance_alerts AS a
                    JOIN surveillance_rules AS r ON r.id = a.rule_id
                    WHERE a.id = %s
                    """,
                    (alert_id,),
                )
                row = cursor.fetchone()
    if row is None:
        return None
    return _alert_from_row(row)


def alert_context(alert):
    """The book stored at the alert's sequence, when that snapshot is still current."""
    symbol = alert.get("symbol")
    sequence = alert.get("ingest_sequence")
    current = get_symbol(symbol) if symbol else None
    matched = None
    if current is not None and sequence is not None and current["ingest_sequence"] == sequence:
        matched = current
    trades = []
    if symbol and sequence is not None:
        with lock():
            conn = connection()
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, price, quantity, received_at
                        FROM trade_observations
                        WHERE symbol = %s AND ingest_sequence = %s
                        ORDER BY id
                        """,
                        (symbol, sequence),
                    )
                    trades = [
                        {
                            "ingestion_id": item[0],
                            "price": float(item[1]),
                            "quantity": float(item[2]),
                            "received_at": item[3].isoformat(),
                        }
                        for item in cursor.fetchall()
                    ]
    return {"book": matched, "current_sequence": None if current is None else current["ingest_sequence"], "trades": trades}


def filter_choices():
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT symbol
                    FROM surveillance_alerts
                    WHERE symbol IS NOT NULL
                    ORDER BY symbol
                    """
                )
                symbols = [row[0] for row in cursor.fetchall()]
                cursor.execute("SELECT name FROM surveillance_rules ORDER BY name")
                rules = [row[0] for row in cursor.fetchall()]
                cursor.execute(
                    """
                    SELECT DISTINCT severity
                    FROM surveillance_alerts
                    ORDER BY severity
                    """
                )
                severities = [row[0] for row in cursor.fetchall()]
    return {"symbols": symbols, "rules": rules, "severities": severities}


def list_rules():
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT name, enabled, threshold, window_seconds
                    FROM surveillance_rules
                    ORDER BY name
                    """
                )
                rows = cursor.fetchall()
    return [
        {
            "name": row[0],
            "enabled": bool(row[1]),
            "threshold": float(row[2]),
            "window_seconds": row[3],
        }
        for row in rows
    ]


def update_rule(name, threshold, enabled):
    if _RULE_NAME.match(name or "") is None:
        return False
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE surveillance_rules
                    SET threshold = %s, enabled = %s, updated_at = now()
                    WHERE name = %s
                    """,
                    (threshold, enabled, name),
                )
                return cursor.rowcount == 1


def timeline():
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.created_at, 'alert', r.name, a.id::text
                    FROM surveillance_alerts AS a
                    JOIN surveillance_rules AS r ON r.id = a.rule_id
                    ORDER BY a.id DESC
                    LIMIT 20
                    """
                )
                alerts = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT created_at, 'scenario', scenario_name, id::text
                    FROM scenario_runs
                    ORDER BY id DESC
                    LIMIT 20
                    """
                )
                runs = cursor.fetchall()
    rows = [
        {"at": row[0].isoformat(), "kind": row[1], "label": row[2], "ref": row[3]}
        for row in alerts + runs
    ]
    rows.sort(key=lambda item: item["at"], reverse=True)
    return rows[:20]
