"""Write validated books into the Postgres read model.

The caller has already normalized the snapshot. This module does not
deduplicate trades across snapshots, and the sequence it assigns is an
ingestion id, not an exchange trade id.
"""

import os

import psycopg
from psycopg.types.json import Json


def database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    return url


class Store(object):
    def __init__(self, url):
        self.connection = psycopg.connect(url)

    def close(self):
        self.connection.close()

    def record(self, book):
        with self.connection:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT nextval('ingest_sequence')")
                sequence = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO market_observations (
                        symbol, received_at, ingest_sequence,
                        exchange_event_time, bids, asks
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        book["symbol"],
                        book["received_at"],
                        sequence,
                        book["exchange_event_time"],
                        Json(book["bids"]),
                        Json(book["asks"]),
                    ),
                )
                observation_id = cursor.fetchone()[0]
                for trade in book["trades"]:
                    cursor.execute(
                        """
                        INSERT INTO trade_observations (
                            observation_id, symbol, received_at,
                            price, quantity, ingest_sequence
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            observation_id,
                            book["symbol"],
                            book["received_at"],
                            trade["price"],
                            trade["quantity"],
                            sequence,
                        ),
                    )
                cursor.execute(
                    """
                    INSERT INTO market_snapshots (
                        symbol, received_at, ingest_sequence,
                        exchange_event_time, status, bids, asks
                    )
                    VALUES (%s, %s, %s, NULL, 'live', %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                        received_at = EXCLUDED.received_at,
                        ingest_sequence = EXCLUDED.ingest_sequence,
                        exchange_event_time = NULL,
                        status = 'live',
                        bids = EXCLUDED.bids,
                        asks = EXCLUDED.asks
                    """,
                    (
                        book["symbol"],
                        book["received_at"],
                        sequence,
                        Json(book["bids"]),
                        Json(book["asks"]),
                    ),
                )
        return sequence
