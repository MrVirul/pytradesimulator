"""Write validated books into the Postgres read model.

The caller has already normalized the snapshot. This module does not
deduplicate trades across snapshots, and the sequence it assigns is an
ingestion id, not an exchange trade id.
"""

import os
import threading

import psycopg
from psycopg.types.json import Json


def database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    return url


class Store(object):
    def __init__(self, url):
        self.url = url
        self.connection = psycopg.connect(url)
        self.lock = threading.Lock()

    def close(self):
        self.connection.close()

    def _ensure(self):
        if self.connection.closed:
            self.connection = psycopg.connect(self.url)

    def record(self, book):
        with self.lock:
            return self._record(book)

    def mark_stale(self):
        """Old books are not the live exchange book after a disconnect or restart."""
        with self.lock:
            self._ensure()
            with self.connection.transaction():
                with self.connection.cursor() as cursor:
                    cursor.execute("UPDATE market_snapshots SET status = 'stale'")
                    cursor.execute(
                        """
                        UPDATE feed_status
                        SET logged_on = FALSE, updated_at = now()
                        WHERE id = 1
                        """
                    )

    def mark_logged_on(self):
        """Logon is feed health. It does not make a stored book live."""
        with self.lock:
            self._ensure()
            with self.connection.transaction():
                with self.connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE feed_status
                        SET logged_on = TRUE, updated_at = now()
                        WHERE id = 1
                        """
                    )

    def _record(self, book):
        self._ensure()
        with self.connection.transaction():
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
