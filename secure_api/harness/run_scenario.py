#!/usr/bin/env python
"""Send one named scenario as CLIENT3.

The process reads the scenario name and then the fixed orders in
secure_api.harness.scenarios. It does not read ORDER_SYMBOL, ORDER_PRICE,
or ORDER_QTY.
"""

import os
import sys
import time
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from secure_api.harness.scenarios import ScenarioError, orders_for, resolve_scenario
from secure_api.tools.fix_baseline import dictionary_path, new_limit, render_config


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        name = resolve_scenario(arguments, os.environ)
    except ScenarioError as error:
        print("scenario: {0}".format(error.reason), flush=True)
        return 2
    symbol, orders = orders_for(name)
    return send_orders(name, symbol, orders)


def send_orders(name, symbol, orders):
    import quickfix as fix

    from secure_api.tools.fix_baseline import OrderApplication, start_initiator

    host = os.environ.get("EXCHANGE_HOST", "127.0.0.1")
    runtime = Path("/tmp/pytradesim-scenario")
    render_config(
        Path(__file__).resolve().parent / "configs" / "client3.cfg",
        runtime / "client3.cfg",
        host,
        runtime / "store",
        runtime / "logs",
        dictionary_path(),
    )
    application = OrderApplication()
    initiator = start_initiator(runtime / "client3.cfg", application)
    try:
        if not application.logged_on.wait(30):
            print("scenario: CLIENT3 did not log on", flush=True)
            return 1
        for index, order in enumerate(orders):
            cl_ord_id = "CLIENT3{0}{1}{2}".format(
                name[:6], int(time.time() * 1000), index
            )
            side = fix.Side_BUY if order["side"] == "buy" else fix.Side_SELL
            message = new_limit(
                cl_ord_id, symbol, order["quantity"], order["price"], side
            )
            if not fix.Session.sendToTarget(message, application.session_id):
                print("scenario: send failed", flush=True)
                return 1
            print(
                "scenario: {0} {1} {2}@{3} {4}".format(
                    name, order["side"], order["quantity"], order["price"], symbol
                ),
                flush=True,
            )
            if not _wait_report(application, cl_ord_id, order["expect"], 20):
                print(
                    "scenario: missing exec_type {0} for {1}".format(
                        order["expect"], cl_ord_id
                    ),
                    flush=True,
                )
                return 1
            # A later order clears trades the gateway has not flushed yet.
            if order.get("pause_after"):
                time.sleep(order["pause_after"])
        print("scenario: PASS {0}".format(name), flush=True)
        return 0
    finally:
        initiator.stop()


def _wait_report(application, cl_ord_id, exec_type, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for report in application.copy_reports():
            if report["cl_ord_id"] == cl_ord_id and report["exec_type"] == exec_type:
                return True
        time.sleep(0.1)
    return False


if __name__ == "__main__":
    sys.exit(main())
