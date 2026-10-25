"""Price, spread, and volume rules store the rule, observed value, threshold, and time."""

import os
import uuid
from datetime import datetime, timezone

import psycopg
import pytest
from psycopg.types.json import Json

from secure_api.app.services.alerts import list_alerts
from secure_api.app.services.surveillance import evaluate_pending, findings


def _rules():
    return [
        {"id": 1, "name": "price_movement", "enabled": True, "threshold": 100},
        {"id": 2, "name": "spread_widening", "enabled": True, "threshold": 5},
        {"id": 3, "name": "volume", "enabled": True, "threshold": 1000},
        {"id": 4, "name": "other", "enabled": True, "threshold": 0},
    ]


def test_crossings_record_observed_value_and_threshold():
    book = {
        "symbol": "RULES",
        "bids": [{"price": 40, "quantity": 1}],
        "asks": [{"price": 50, "quantity": 1}],
        "trades": [{"price": 150, "quantity": 10}],
    }
    found = findings(_rules(), book, 1100)
    by_name = {item["rule_name"]: item for item in found}
    assert set(by_name) == {"price_movement", "spread_widening", "volume"}
    assert by_name["price_movement"]["observed_value"] == 150
    assert by_name["price_movement"]["threshold"] == 100
    assert by_name["spread_widening"]["observed_value"] == 10
    assert by_name["spread_widening"]["threshold"] == 5
    assert by_name["volume"]["observed_value"] == 1100
    assert by_name["volume"]["threshold"] == 1000


def test_quiet_book_and_disabled_rule_do_not_alert():
    book = {
        "symbol": "RULES",
        "bids": [{"price": 40, "quantity": 1}],
        "asks": [],
        "trades": [],
    }
    assert findings(_rules(), book, 0) == []
    disabled = [
        {"id": 1, "name": "price_movement", "enabled": False, "threshold": 1},
    ]
    priced = {
        "symbol": "RULES",
        "bids": [{"price": 150, "quantity": 1}],
        "asks": [],
        "trades": [],
    }
    assert findings(disabled, priced, 0) == []


def test_price_uses_the_best_bid_when_the_snapshot_has_no_trade():
    book = {
        "symbol": "RULES",
        "bids": [{"price": 53, "quantity": 7}, {"price": 150, "quantity": 1}],
        "asks": [{"price": 140, "quantity": 1}],
        "trades": [],
    }
    found = findings(_rules(), book, 0)
    by_name = {item["rule_name"]: item for item in found}
    assert by_name["price_movement"]["observed_value"] == 150
    assert "spread_widening" not in by_name


def _insert_observation(symbol, bids, asks, trades):
    received_at = datetime.now(timezone.utc)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO market_observations (
                    symbol, received_at, ingest_sequence, exchange_event_time, bids, asks
                )
                VALUES (%s, %s, nextval('ingest_sequence'), NULL, %s, %s)
                RETURNING id, ingest_sequence
                """,
                (symbol, received_at, Json(bids), Json(asks)),
            )
            observation_id, sequence = cursor.fetchone()
            for trade in trades:
                cursor.execute(
                    """
                    INSERT INTO trade_observations (
                        observation_id, symbol, received_at, price, quantity, ingest_sequence
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        observation_id,
                        symbol,
                        received_at,
                        trade["price"],
                        trade["quantity"],
                        sequence,
                    ),
                )
    return received_at


def test_stored_alert_keeps_rule_observed_value_threshold_and_time():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    symbol = "R{0}".format(uuid.uuid4().hex[:8].upper())
    quiet = "Q{0}".format(uuid.uuid4().hex[:8].upper())
    received_at = _insert_observation(
        symbol,
        [{"price": 40, "quantity": 1}],
        [{"price": 50, "quantity": 1}],
        [{"price": 150, "quantity": 1100}],
    )
    _insert_observation(quiet, [{"price": 10, "quantity": 1}], [], [])
    evaluate_pending()
    rows = list_alerts(symbol, "", "")
    by_name = {row["rule_name"]: row for row in rows}
    assert set(by_name) == {"price_movement", "spread_widening", "volume"}
    assert by_name["price_movement"]["observed_value"] == 150
    assert by_name["price_movement"]["threshold"] == 100
    assert by_name["spread_widening"]["observed_value"] == 10
    assert by_name["spread_widening"]["threshold"] == 5
    assert by_name["volume"]["observed_value"] == 1100
    assert by_name["volume"]["threshold"] == 1000
    for row in rows:
        assert row["created_at"].startswith(received_at.date().isoformat())
    assert list_alerts(quiet, "", "") == []
    evaluate_pending()
    assert len(list_alerts(symbol, "", "")) == 3
