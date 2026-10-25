#!/usr/bin/env python
"""Scripted FIX baseline against a running pytradesim exchange.

Runs inside the legacy image, which is where QuickFIX is installed.
MDCLIENT3 subscribes on logon. CLIENT3 rests a limit bid, waits for the
snapshot, then sells the same size at the same price.

Exit 0 when the execution reports and both 35=W snapshots match.
Exit 1 otherwise. This file is not named test_*.py, so pytest does not
collect it and CI does not need a running exchange.
"""

import os
import re
import sys
import threading
import time
from pathlib import Path

import quickfix as fix
import quickfix42 as fix42


ROOT = Path(__file__).resolve().parents[1]
MD_CONFIG = ROOT / "adapter" / "configs" / "mdclient3.cfg"
ORDER_CONFIG = ROOT / "harness" / "configs" / "client3.cfg"
LOGON_TIMEOUT = 30.0
SNAPSHOT_TIMEOUT = 20.0
PRICE_TOLERANCE = 1e-6


def fail(message):
    print("baseline: {0}".format(message), flush=True)
    return 1


def load_symbol():
    symbol = os.environ.get("BASELINE_SYMBOL", "BASELINE")
    if not re.fullmatch(r"[A-Z0-9]{1,16}", symbol):
        raise SystemExit(
            "BASELINE_SYMBOL must be 1-16 uppercase letters or digits"
        )
    return symbol


def load_number(name, default):
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError:
        raise SystemExit("{0} must be a number".format(name))
    if value <= 0:
        raise SystemExit("{0} must be positive".format(name))
    return value


def dictionary_path():
    override = os.environ.get("FIX_DATA_DICTIONARY")
    if override:
        path = Path(override)
    else:
        packaged = Path("/app/pytradesim/spec/FIX42.xml")
        repo = ROOT.parents[0] / "pytradesim" / "spec" / "FIX42.xml"
        path = packaged if packaged.is_file() else repo
    if not path.is_file():
        raise SystemExit("FIX data dictionary not found at {0}".format(path))
    return path


def render_config(source, destination, host, store, logs, dictionary):
    store.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    replacements = {
        "SocketConnectHost": host,
        "FileStorePath": store.as_posix(),
        "FileLogPath": logs.as_posix(),
        "DataDictionary": dictionary.as_posix(),
    }
    lines = []
    seen_reset = False
    for line in source.read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0]
        if key in replacements:
            lines.append("{0}={1}".format(key, replacements[key]))
        else:
            lines.append(line)
        if key == "ResetOnLogon":
            seen_reset = True
    if not seen_reset:
        lines.append("ResetOnLogon=Y")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def close_enough(left, right):
    return abs(float(left) - float(right)) < PRICE_TOLERANCE


def has_level(levels, price, quantity):
    for level_price, level_quantity in levels:
        if close_enough(level_price, price) and close_enough(level_quantity, quantity):
            return True
    return False


def header_type(message):
    msg_type = fix.MsgType()
    message.getHeader().getField(msg_type)
    return msg_type.getValue()


def field_value(message, field):
    try:
        message.getField(field)
    except fix.FieldNotFound:
        return None
    return field.getValue()


class MarketApplication(fix.Application):
    """MDCLIENT3. Subscribes once, from onLogon, and records 35=W."""

    def __init__(self, symbol):
        super(MarketApplication, self).__init__()
        self.symbol = symbol
        self.logged_on = threading.Event()
        self.session_id = None
        self.subscribed = False
        self.subscribe_lock = threading.Lock()
        self.snapshots = []
        self.lock = threading.Lock()

    def onCreate(self, sessionID):
        return

    def onLogon(self, sessionID):
        self.session_id = sessionID
        print("baseline: MDCLIENT3 logged on", flush=True)
        self.logged_on.set()
        # sendToTarget from inside onLogon can deadlock QuickFIX. The
        # subscribe still happens because of the logon, on another thread.
        thread = threading.Thread(
            target=self._subscribe_after_logon, args=(sessionID,)
        )
        thread.daemon = True
        thread.start()

    def _subscribe_after_logon(self, sessionID):
        time.sleep(0.2)
        self.send_subscribe(sessionID)

    def onLogout(self, sessionID):
        print("baseline: MDCLIENT3 logged out", flush=True)

    def toAdmin(self, message, sessionID):
        return

    def fromAdmin(self, message, sessionID):
        return

    def toApp(self, message, sessionID):
        return

    def fromApp(self, message, sessionID):
        try:
            if header_type(message) != "W":
                return
            snapshot = parse_snapshot(message)
        except Exception as error:
            print("baseline: bad snapshot: {0}".format(error), flush=True)
            return
        with self.lock:
            self.snapshots.append(snapshot)
        print(
            "baseline: 35=W {0} bids={1} asks={2} trades={3}".format(
                snapshot["symbol"],
                snapshot["bids"],
                snapshot["asks"],
                snapshot["trades"],
            ),
            flush=True,
        )

    def send_subscribe(self, sessionID):
        with self.subscribe_lock:
            if self.subscribed:
                return True
            sent = fix.Session.sendToTarget(
                market_data_request(self.symbol), sessionID
            )
            if sent:
                self.subscribed = True
                print(
                    "baseline: subscribed to {0}".format(self.symbol), flush=True
                )
            return sent

    def copy_snapshots(self):
        with self.lock:
            return list(self.snapshots)


class OrderApplication(fix.Application):
    """CLIENT3. Records execution reports for the scripted orders."""

    def __init__(self):
        super(OrderApplication, self).__init__()
        self.logged_on = threading.Event()
        self.session_id = None
        self.reports = []
        self.lock = threading.Lock()

    def onCreate(self, sessionID):
        return

    def onLogon(self, sessionID):
        self.session_id = sessionID
        print("baseline: CLIENT3 logged on", flush=True)
        self.logged_on.set()

    def onLogout(self, sessionID):
        print("baseline: CLIENT3 logged out", flush=True)

    def toAdmin(self, message, sessionID):
        return

    def fromAdmin(self, message, sessionID):
        return

    def toApp(self, message, sessionID):
        return

    def fromApp(self, message, sessionID):
        try:
            if header_type(message) != "8":
                return
            report = parse_execution(message)
        except Exception as error:
            print("baseline: bad execution report: {0}".format(error), flush=True)
            return
        with self.lock:
            self.reports.append(report)
        print(
            "baseline: 35=8 exec_type={0} symbol={1} last={2}@{3}".format(
                report["exec_type"],
                report["symbol"],
                report["quantity"],
                report["price"],
            ),
            flush=True,
        )

    def copy_reports(self):
        with self.lock:
            return list(self.reports)


def market_data_request(symbol):
    message = fix42.MarketDataRequest()
    header = message.getHeader()
    header.setField(fix.SenderCompID("MDCLIENT3"))
    header.setField(fix.TargetCompID("MARKET"))
    message.setField(fix.MDReqID("BASELINE"))
    message.setField(
        fix.SubscriptionRequestType(
            fix.SubscriptionRequestType_SNAPSHOT_PLUS_UPDATES
        )
    )
    message.setField(fix.MarketDepth(10))

    entry_types = fix42.MarketDataRequest().NoMDEntryTypes()
    for entry_type in (
        fix.MDEntryType_BID,
        fix.MDEntryType_OFFER,
        fix.MDEntryType_TRADE,
    ):
        entry_types.setField(fix.MDEntryType(entry_type))
        message.addGroup(entry_types)

    symbols = fix42.MarketDataRequest().NoRelatedSym()
    symbols.setField(fix.Symbol(symbol))
    message.addGroup(symbols)
    return message


def new_limit(cl_ord_id, symbol, quantity, price, side):
    message = fix.Message()
    header = message.getHeader()
    header.setField(fix.BeginString("FIX.4.2"))
    header.setField(fix.SenderCompID("CLIENT3"))
    header.setField(fix.TargetCompID("EXCHANGE"))
    header.setField(fix.MsgType("D"))
    message.setField(fix.ClOrdID(cl_ord_id))
    message.setField(fix.Symbol(symbol))
    message.setField(fix.Side(side))
    message.setField(fix.Price(float(price)))
    message.setField(fix.OrdType(fix.OrdType_LIMIT))
    message.setField(fix.HandlInst(fix.HandlInst_MANUAL_ORDER_BEST_EXECUTION))
    message.setField(fix.TransactTime())
    message.setField(fix.OrderQty(float(quantity)))
    return message


def parse_snapshot(message):
    symbol = field_value(message, fix.Symbol())
    bids = []
    asks = []
    trades = []
    count = field_value(message, fix.NoMDEntries())
    if count is not None:
        group = fix42.MarketDataSnapshotFullRefresh().NoMDEntries()
        for index in range(int(count)):
            message.getGroup(index + 1, group)
            entry_type = field_value(group, fix.MDEntryType())
            price = field_value(group, fix.MDEntryPx())
            quantity = field_value(group, fix.MDEntrySize())
            level = (price, quantity)
            if entry_type == "0":
                bids.append(level)
            elif entry_type == "1":
                asks.append(level)
            elif entry_type == "2":
                trades.append(level)
    return {"symbol": symbol, "bids": bids, "asks": asks, "trades": trades}


def parse_execution(message):
    return {
        "exec_type": field_value(message, fix.ExecType()),
        "symbol": field_value(message, fix.Symbol()),
        "price": field_value(message, fix.LastPx()),
        "quantity": field_value(message, fix.LastQty()),
        "cl_ord_id": field_value(message, fix.ClOrdID()),
    }


def start_initiator(config_path, application):
    settings = fix.SessionSettings(str(config_path))
    initiator = fix.SocketInitiator(
        application,
        fix.FileStoreFactory(settings),
        settings,
        fix.FileLogFactory(settings),
    )
    initiator.start()
    return initiator


def wait_until(predicate, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def saw_resting(snapshots, symbol, price, quantity):
    for snapshot in snapshots:
        if snapshot["symbol"] != symbol:
            continue
        if has_level(snapshot["bids"], price, quantity):
            return True
    return False


def saw_cross(snapshots, symbol, price, quantity):
    resting_at = None
    for index, snapshot in enumerate(snapshots):
        if snapshot["symbol"] != symbol:
            continue
        if has_level(snapshot["bids"], price, quantity):
            resting_at = index
            break
    if resting_at is None:
        return False
    for snapshot in snapshots[resting_at + 1:]:
        if snapshot["symbol"] != symbol:
            continue
        if snapshot["bids"] or snapshot["asks"]:
            continue
        if has_level(snapshot["trades"], price, quantity):
            return True
    return False


def reports_ok(reports, symbol):
    types = [
        report["exec_type"]
        for report in reports
        if report["symbol"] == symbol and report["exec_type"] is not None
    ]
    if not types or types[0] != "0":
        return False
    return types.count("2") >= 2


def send_order(application, cl_ord_id, symbol, quantity, price, side):
    message = new_limit(cl_ord_id, symbol, quantity, price, side)
    if not fix.Session.sendToTarget(message, application.session_id):
        raise RuntimeError("send failed for {0}".format(cl_ord_id))
    print("baseline: sent {0}".format(cl_ord_id), flush=True)


def evaluate(market, orders, symbol, price, quantity):
    problems = []
    snapshots = market.copy_snapshots()
    reports = orders.copy_reports()
    if not market.subscribed:
        problems.append("MDCLIENT3 did not subscribe")
    if not saw_resting(snapshots, symbol, price, quantity):
        problems.append(
            "no 35=W bid ({0}, {1}) for {2}".format(price, quantity, symbol)
        )
    if not saw_cross(snapshots, symbol, price, quantity):
        problems.append(
            "no flat 35=W with trade ({0}, {1})".format(price, quantity)
        )
    if not reports_ok(reports, symbol):
        problems.append(
            "expected exec types 0 then two 2s, got {0}".format(
                [report["exec_type"] for report in reports]
            )
        )
    return problems


def main():
    symbol = load_symbol()
    price = load_number("BASELINE_PRICE", 189)
    quantity = load_number("BASELINE_QTY", 675)
    host = os.environ.get("EXCHANGE_HOST", "127.0.0.1")
    dictionary = dictionary_path()
    runtime = Path("/tmp/pytradesim-baseline")
    render_config(
        MD_CONFIG,
        runtime / "mdclient3.cfg",
        host,
        runtime / "md" / "store",
        runtime / "md" / "logs",
        dictionary,
    )
    render_config(
        ORDER_CONFIG,
        runtime / "client3.cfg",
        host,
        runtime / "order" / "store",
        runtime / "order" / "logs",
        dictionary,
    )

    market = MarketApplication(symbol)
    orders = OrderApplication()
    market_initiator = None
    order_initiator = None
    problems = []
    try:
        market_initiator = start_initiator(runtime / "mdclient3.cfg", market)
        if not market.logged_on.wait(LOGON_TIMEOUT):
            return fail("MDCLIENT3 did not log on within {0}s".format(LOGON_TIMEOUT))
        if not market.subscribed:
            market.send_subscribe(market.session_id)
        # The acceptor records the subscription before the next flush.
        time.sleep(1.0)

        order_initiator = start_initiator(runtime / "client3.cfg", orders)
        if not orders.logged_on.wait(LOGON_TIMEOUT):
            return fail("CLIENT3 did not log on within {0}s".format(LOGON_TIMEOUT))

        send_order(
            orders, "CLIENT3{0}1".format(symbol), symbol, quantity, price, fix.Side_BUY
        )
        resting = wait_until(
            lambda: saw_resting(market.copy_snapshots(), symbol, price, quantity),
            SNAPSHOT_TIMEOUT,
        )
        if not resting:
            problems.append("resting bid was not published")
        else:
            # One flush is about a second. The cross has to be a later snapshot.
            time.sleep(1.0)
            send_order(
                orders,
                "CLIENT3{0}2".format(symbol),
                symbol,
                quantity,
                price,
                fix.Side_SELL,
            )
            wait_until(
                lambda: reports_ok(orders.copy_reports(), symbol)
                and saw_cross(market.copy_snapshots(), symbol, price, quantity),
                SNAPSHOT_TIMEOUT,
            )
        problems.extend(evaluate(market, orders, symbol, price, quantity))
    except Exception as error:
        problems.append(str(error))
    finally:
        if order_initiator is not None:
            order_initiator.stop()
        if market_initiator is not None:
            market_initiator.stop()

    if problems:
        for problem in problems:
            print("baseline: FAIL {0}".format(problem), flush=True)
        print("baseline: FIX logs under {0}".format(runtime), flush=True)
        return 1
    print(
        "baseline: PASS {0} bid {1} x {2} crossed".format(symbol, quantity, price),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
