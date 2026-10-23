"""Queue a named scenario. This module does not import QuickFIX or send an order."""

from secure_api.app.db import connection, lock
from secure_api.app.services.scenario_checks import CheckFailed, run_access_scenario
from secure_api.harness.scenarios import ACCESS_SCENARIOS, SCENARIOS, orders_for

LAB_SCENARIOS = (
    "price_movement",
    "spread_widening",
    "volume",
    "unauthorized_access",
    "rate_limit_abuse",
)


_EXPECTS = {
    "price_movement": "price_movement on PRICE",
    "spread_widening": "spread_widening on SPREAD",
    "volume": "volume on VOLUME",
    "unauthorized_access": "a 403 on the audit log",
    "rate_limit_abuse": "a 429 on a market read",
}

_ABOUT = {
    "price_movement": "Prints a trade above the price rule.",
    "spread_widening": "Rests a wide market on SPREAD.",
    "volume": "Fills enough size to cross the volume rule.",
    "unauthorized_access": "A market-data client reads the audit log.",
    "rate_limit_abuse": "Reads the book again inside the same limit window.",
}


def scenario_choices():
    cards = []
    for name in LAB_SCENARIOS:
        lines = []
        if name in SCENARIOS:
            _symbol, orders = orders_for(name)
            for order in orders:
                lines.append(
                    "{0} {1} @ {2}".format(order["side"], order["quantity"], order["price"])
                )
        cards.append(
            {
                "name": name,
                "runnable": name in SCENARIOS or name in ACCESS_SCENARIOS,
                "orders": lines,
                "sends_order": name in SCENARIOS,
                "about": _ABOUT[name],
                "expects": _EXPECTS[name],
            }
        )
    return cards


def _request_id(detail):
    if isinstance(detail, str) and detail.startswith("req-"):
        return detail
    return ""


def _insert(name, client_id, status, detail, symbol):
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO scenario_runs (
                        scenario_name, requested_by, status, detail, finished_at
                    )
                    VALUES (%s, %s, %s, %s, CASE WHEN %s = 'pending' THEN NULL ELSE now() END)
                    RETURNING id
                    """,
                    (name, client_id, status, detail, status),
                )
                run_id = cursor.fetchone()[0]
    return {
        "id": run_id,
        "scenario": name,
        "status": status,
        "symbol": symbol,
        "request_id": _request_id(detail),
    }


def start_named(name, client_id):
    if name in ACCESS_SCENARIOS:
        try:
            outcome = run_access_scenario(name)
        except (CheckFailed, Exception):
            return _insert(name, client_id, "failed", "unavailable", "")
        return _insert(name, client_id, outcome["status"], outcome["detail"], "")
    return enqueue(name, client_id)


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
    return _insert(name, client_id, "pending", "", symbol)


def recent_runs(limit=12):
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, scenario_name, status, detail, created_at
                    FROM scenario_runs
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
    return [
        {
            "id": row[0],
            "scenario": row[1],
            "status": row[2],
            "request_id": _request_id(row[3]),
            "created_at": row[4].isoformat(),
        }
        for row in rows
    ]


def get_run(run_id):
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, scenario_name, status, detail
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
        "request_id": _request_id(row[3]),
    }
