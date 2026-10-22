#!/usr/bin/env python
"""Place one resting bid as CLIENT3.

Used to show that a legacy order reaches the read model through the
subscriber. This process does not open the market-data session.
"""

import os
import sys
import time
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import quickfix as fix

from secure_api.tools.fix_baseline import (
    OrderApplication,
    dictionary_path,
    new_limit,
    render_config,
    start_initiator,
)


def main():
    symbol = os.environ.get("ORDER_SYMBOL", "BASELINE")
    price = float(os.environ.get("ORDER_PRICE", "51"))
    quantity = float(os.environ.get("ORDER_QTY", "40"))
    host = os.environ.get("EXCHANGE_HOST", "127.0.0.1")
    runtime = Path("/tmp/pytradesim-order")
    render_config(
        Path(__file__).resolve().parent / "configs" / "client3.cfg",
        runtime / "client3.cfg",
        host,
        runtime / "store",
        runtime / "logs",
        dictionary_path(),
    )
    orders = OrderApplication()
    initiator = start_initiator(runtime / "client3.cfg", orders)
    try:
        if not orders.logged_on.wait(30):
            print("order: CLIENT3 did not log on", flush=True)
            return 1
        message = new_limit(
            "CLIENT3{0}{1}".format(symbol, int(time.time() * 1000)),
            symbol,
            quantity,
            price,
            fix.Side_BUY,
        )
        if not fix.Session.sendToTarget(message, orders.session_id):
            print("order: send failed", flush=True)
            return 1
        print("order: sent bid {0} {1}@{2}".format(symbol, quantity, price), flush=True)
        deadline = time.time() + 20
        while time.time() < deadline:
            reports = orders.copy_reports()
            if any(report["exec_type"] == "0" for report in reports):
                print("order: accepted", flush=True)
                return 0
            time.sleep(0.1)
        print("order: no acknowledgement", flush=True)
        return 1
    finally:
        initiator.stop()


if __name__ == "__main__":
    sys.exit(main())
