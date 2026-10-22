"""Read surveillance alerts. Filters are checked before the query."""

import re

from secure_api.app.db import connection, lock
from secure_api.app.services.market_data import SYMBOL_PATTERN

_SEVERITY = re.compile(r"^[a-z]{3,16}$")
_RULE_NAME = re.compile(r"^[A-Za-z0-9_. -]{1,64}$")


def filter_error(symbol, severity, rule_name):
    if symbol and SYMBOL_PATTERN.match(symbol) is None:
        return "invalid_symbol"
    if severity and _SEVERITY.match(severity) is None:
        return "invalid_severity"
    if rule_name and _RULE_NAME.match(rule_name) is None:
        return "invalid_rule"
    return None


def list_alerts(symbol, severity, rule_name):
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
