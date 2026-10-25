#!/usr/bin/env python
"""Run queued scenario names as CLIENT3.

The API inserts the name. This process, on the legacy image, sends the
fixed orders. It does not read a price, quantity, or symbol from the row.
"""

import os
import sys
import time
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import psycopg

from secure_api.harness.run_scenario import send_orders
from secure_api.harness.scenarios import orders_for


def log(message):
    print("scenario-worker: {0}".format(message), flush=True)


def _connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    return psycopg.connect(url)


def claim():
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE scenario_runs
                SET status = 'running'
                WHERE id = (
                    SELECT id
                    FROM scenario_runs
                    WHERE status = 'pending'
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING id, scenario_name
                """
            )
            return cursor.fetchone()


def finish(run_id, status, detail):
    with _connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE scenario_runs
                SET status = %s, detail = %s, finished_at = now()
                WHERE id = %s
                """,
                (status, detail, run_id),
            )


def run_once():
    row = claim()
    if row is None:
        return False
    run_id, name = row
    log("start {0} {1}".format(run_id, name))
    try:
        symbol, orders = orders_for(name)
        code = send_orders(name, symbol, orders)
    except Exception:
        finish(run_id, "failed", "error")
        log("failed {0}".format(run_id))
        return True
    if code == 0:
        finish(run_id, "passed", "passed")
        log("passed {0}".format(run_id))
    else:
        finish(run_id, "failed", "not_acknowledged")
        log("failed {0}".format(run_id))
    return True


def main():
    while True:
        try:
            worked = run_once()
        except Exception:
            log("wait")
            worked = False
        if not worked:
            time.sleep(1)


if __name__ == "__main__":
    main()
