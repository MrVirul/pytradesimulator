"""Price, spread, and volume rules over stored books.

The subscriber only writes observations. This module runs in the API
process. An alert is stored when the observed value is above the rule
threshold, with that threshold and the observation time. The same
observation is not alerted twice.
"""

import json
import time
from datetime import timedelta

from secure_api.app.db import connection, lock

RULES = ("price_movement", "spread_widening", "volume")


def _levels(value):
    if isinstance(value, str):
        return json.loads(value)
    if value is None:
        return []
    return value


def _best_bid(bids):
    if not bids:
        return None
    return max(float(level["price"]) for level in bids)


def _best_ask(asks):
    if not asks:
        return None
    return min(float(level["price"]) for level in asks)


def observed_value(rule_name, book, trade_quantity):
    """Return the measured value, or None when this book cannot answer the rule."""
    if rule_name == "price_movement":
        trades = book.get("trades") or []
        if trades:
            return max(float(trade["price"]) for trade in trades)
        return _best_bid(_levels(book.get("bids")))
    if rule_name == "spread_widening":
        bid = _best_bid(_levels(book.get("bids")))
        ask = _best_ask(_levels(book.get("asks")))
        if bid is None or ask is None or ask < bid:
            return None
        return ask - bid
    if rule_name == "volume":
        return float(trade_quantity)
    return None


def findings(rules, book, trade_quantity):
    """Rules whose observed value is above the stored threshold."""
    found = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        name = rule["name"]
        measured = observed_value(name, book, trade_quantity)
        if measured is None or measured <= float(rule["threshold"]):
            continue
        threshold = float(rule["threshold"])
        found.append(
            {
                "rule_id": rule["id"],
                "rule_name": name,
                "symbol": book["symbol"],
                "severity": "warning",
                "observed_value": float(measured),
                "threshold": threshold,
                "detail": "{0} observed {1} above {2}".format(name, measured, threshold),
            }
        )
    return found


def _load_rules(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, name, enabled, threshold, window_seconds
            FROM surveillance_rules
            WHERE enabled AND name = ANY(%s)
            """,
            (list(RULES),),
        )
        return [
            {
                "id": row[0],
                "name": row[1],
                "enabled": row[2],
                "threshold": float(row[3]),
                "window_seconds": row[4],
            }
            for row in cursor.fetchall()
        ]


def _pending(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT o.id, o.symbol, o.received_at, o.ingest_sequence, o.bids, o.asks
            FROM market_observations AS o
            LEFT JOIN surveillance_checkpoints AS c ON c.symbol = o.symbol
            WHERE o.ingest_sequence > COALESCE(c.ingest_sequence, 0)
            ORDER BY o.ingest_sequence
            """
        )
        return cursor.fetchall()


def _observation_trades(conn, observation_id):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT price, quantity
            FROM trade_observations
            WHERE observation_id = %s
            """,
            (observation_id,),
        )
        return [
            {"price": float(row[0]), "quantity": float(row[1])}
            for row in cursor.fetchall()
        ]


def _trade_quantity(conn, observation_id, symbol, received_at, rules):
    window = None
    for rule in rules:
        if rule["name"] == "volume":
            window = rule["window_seconds"]
    with conn.cursor() as cursor:
        if window:
            start = received_at - timedelta(seconds=int(window))
            cursor.execute(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM trade_observations
                WHERE symbol = %s AND received_at >= %s AND received_at <= %s
                """,
                (symbol, start, received_at),
            )
        else:
            cursor.execute(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM trade_observations
                WHERE observation_id = %s
                """,
                (observation_id,),
            )
        return float(cursor.fetchone()[0])


def _insert_alert(conn, alert, received_at, sequence):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO surveillance_alerts (
                rule_id, symbol, severity, observed_value, threshold,
                created_at, detail, ingest_sequence
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (rule_id, symbol, ingest_sequence) DO NOTHING
            """,
            (
                alert["rule_id"],
                alert["symbol"],
                alert["severity"],
                alert["observed_value"],
                alert["threshold"],
                received_at,
                alert["detail"],
                sequence,
            ),
        )
        return cursor.rowcount == 1


def _advance(conn, symbol, sequence):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO surveillance_checkpoints (symbol, ingest_sequence)
            VALUES (%s, %s)
            ON CONFLICT (symbol) DO UPDATE
            SET ingest_sequence = EXCLUDED.ingest_sequence
            WHERE surveillance_checkpoints.ingest_sequence < EXCLUDED.ingest_sequence
            """,
            (symbol, sequence),
        )


def evaluate_pending():
    """Write alerts for observations the API has not judged yet."""
    written = 0
    with lock():
        conn = connection()
        with conn.transaction():
            rules = _load_rules(conn)
            latest = {}
            for row in _pending(conn):
                book = {
                    "symbol": row[1],
                    "bids": _levels(row[4]),
                    "asks": _levels(row[5]),
                    "trades": _observation_trades(conn, row[0]),
                }
                quantity = _trade_quantity(conn, row[0], row[1], row[2], rules)
                for alert in findings(rules, book, quantity):
                    if _insert_alert(conn, alert, row[2], row[3]):
                        written += 1
                latest[row[1]] = row[3]
            for symbol, sequence in latest.items():
                _advance(conn, symbol, sequence)
    return written


def watch_books(interval_seconds=2):
    """Poll stored books until the process exits."""
    while True:
        try:
            evaluate_pending()
        except Exception:
            pass
        time.sleep(interval_seconds)
