"""Queue a named scenario. This module does not import QuickFIX or send an order."""

from secure_api.app.db import connection, lock
from secure_api.harness.scenarios import SCENARIOS, orders_for

LAB_SCENARIOS = (
    "price_movement",
    "spread_widening",
    "volume",
    "unauthorized_access",
    "rate_limit_abuse",
)


def scenario_choices():
    return [
        {"name": name, "runnable": name in SCENARIOS} for name in LAB_SCENARIOS
    ]


def scenario_policy():
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT requests_allowed, window_seconds
                    FROM rate_limit_policies
                    WHERE category = 'scenario'
                      AND subject IN ('security_admin', '*')
                    ORDER BY CASE subject WHEN 'security_admin' THEN 0 ELSE 1 END
                    LIMIT 1
                    """
                )
                row = cursor.fetchone()
    if row is None:
        return {"requests_allowed": 3, "window_seconds": 60}
    return {"requests_allowed": row[0], "window_seconds": row[1]}


def enqueue(name, client_id):
    symbol, _orders = orders_for(name)
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO scenario_runs (scenario_name, requested_by, status)
                    VALUES (%s, %s, 'pending')
                    RETURNING id
                    """,
                    (name, client_id),
                )
                run_id = cursor.fetchone()[0]
    return {
        "id": run_id,
        "scenario": name,
        "status": "pending",
        "symbol": symbol,
    }


def get_run(run_id):
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, scenario_name, status
                    FROM scenario_runs
                    WHERE id = %s
                    """,
                    (run_id,),
                )
                row = cursor.fetchone()
    if row is None:
        return None
    symbol = ""
    if row[1] in SCENARIOS:
        symbol, _orders = orders_for(row[1])
    return {
        "id": row[0],
        "scenario": row[1],
        "status": row[2],
        "symbol": symbol,
    }
