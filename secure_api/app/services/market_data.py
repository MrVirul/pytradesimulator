"""Read the latest book and recent trades. Rows are already validated."""

import json
import re

from secure_api.app.db import connection, lock

SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{1,16}$")


def _levels(value):
    if isinstance(value, str):
        value = json.loads(value)
    if not value:
        return []
    return [
        {"price": float(level["price"]), "quantity": float(level["quantity"])}
        for level in value
    ]


def list_symbols():
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT symbol, status, received_at, ingest_sequence,
                           exchange_event_time
                    FROM market_snapshots
                    ORDER BY symbol
                    """
                )
                rows = cursor.fetchall()
    return [
        {
            "symbol": row[0],
            "status": row[1],
            "received_at": row[2].isoformat(),
            "ingest_sequence": row[3],
            "exchange_event_time": None if row[4] is None else row[4].isoformat(),
        }
        for row in rows
    ]


def get_symbol(symbol):
    if SYMBOL_PATTERN.match(symbol or "") is None:
        return None
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT symbol, status, received_at, ingest_sequence,
                           exchange_event_time, bids, asks
                    FROM market_snapshots
                    WHERE symbol = %s
                    """,
                    (symbol,),
                )
                row = cursor.fetchone()
    if row is None:
        return None
    return {
        "symbol": row[0],
        "status": row[1],
        "received_at": row[2].isoformat(),
        "ingest_sequence": row[3],
        "exchange_event_time": None if row[4] is None else row[4].isoformat(),
        "bids": _levels(row[5]),
        "asks": _levels(row[6]),
    }


def recent_trades(symbol, limit):
    if SYMBOL_PATTERN.match(symbol or "") is None:
        return None
    bounded = min(max(int(limit), 1), 100)
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, price, quantity, received_at, ingest_sequence
                    FROM trade_observations
                    WHERE symbol = %s
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (symbol, bounded),
                )
                rows = cursor.fetchall()
    return [
        {
            "ingestion_id": row[0],
            "price": float(row[1]),
            "quantity": float(row[2]),
            "received_at": row[3].isoformat(),
            "ingest_sequence": row[4],
        }
        for row in rows
    ]
