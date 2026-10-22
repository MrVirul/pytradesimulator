#!/usr/bin/env python
"""FIX market-data subscriber.

Runs as its own process, from the legacy image, so a web worker cannot
open a second MDCLIENT3 session. It subscribes from onLogon, including
after QuickFIX reconnects, and normalizes each 35=W before doing
anything else with it.
"""

import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import quickfix as fix
import quickfix42 as fix42

from secure_api.adapter.normalizer import RejectedSnapshot, normalize
from secure_api.adapter.persistence import Store, database_url


CONFIG = Path(__file__).resolve().parent / "configs" / "mdclient3.cfg"
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{1,16}$")


def log(message):
    print("subscriber: {0}".format(message), flush=True)


def load_symbols():
    raw = os.environ.get("SUBSCRIBE_SYMBOLS", "MSFT,HYG,BASELINE")
    symbols = [part.strip() for part in raw.split(",") if part.strip()]
    if not symbols:
        raise SystemExit("SUBSCRIBE_SYMBOLS is empty")
    for symbol in symbols:
        if SYMBOL_PATTERN.match(symbol) is None:
            raise SystemExit("invalid symbol {0}".format(symbol))
    return symbols


def dictionary_path():
    override = os.environ.get("FIX_DATA_DICTIONARY")
    path = Path(override) if override else Path("/app/pytradesim/spec/FIX42.xml")
    if not path.is_file():
        raise SystemExit("FIX data dictionary not found at {0}".format(path))
    return path


def render_config(host, dictionary):
    runtime = Path("/tmp/pytradesim-subscriber")
    store = runtime / "store"
    logs = runtime / "logs"
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
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0]
        if key in replacements:
            lines.append("{0}={1}".format(key, replacements[key]))
        else:
            lines.append(line)
        if key == "ResetOnLogon":
            seen_reset = True
    if not seen_reset:
        lines.append("ResetOnLogon=Y")
    destination = runtime / "mdclient3.cfg"
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


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


def snapshot_entries(message):
    entries = []
    count = field_value(message, fix.NoMDEntries())
    if count is None:
        return field_value(message, fix.Symbol()), entries
    group = fix42.MarketDataSnapshotFullRefresh().NoMDEntries()
    for index in range(int(count)):
        message.getGroup(index + 1, group)
        entries.append(
            {
                "type": field_value(group, fix.MDEntryType()),
                "price": field_value(group, fix.MDEntryPx()),
                "quantity": field_value(group, fix.MDEntrySize()),
            }
        )
    return field_value(message, fix.Symbol()), entries


def market_data_request(symbols):
    message = fix42.MarketDataRequest()
    header = message.getHeader()
    header.setField(fix.SenderCompID("MDCLIENT3"))
    header.setField(fix.TargetCompID("MARKET"))
    message.setField(fix.MDReqID("SUBSCRIBER"))
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
    related = fix42.MarketDataRequest().NoRelatedSym()
    for symbol in symbols:
        related.setField(fix.Symbol(symbol))
        message.addGroup(related)
    return message


class Subscriber(fix.Application):
    def __init__(self, symbols, store):
        super(Subscriber, self).__init__()
        self.symbols = symbols
        self.store = store
        self.logged_on = threading.Event()
        self.lock = threading.Lock()
        self.subscribed = False
        self.session_id = None

    def onCreate(self, sessionID):
        return

    def onLogon(self, sessionID):
        self.session_id = sessionID
        self.logged_on.set()
        log("MDCLIENT3 logged on")
        thread = threading.Thread(target=self._subscribe_after_logon, args=(sessionID,))
        thread.daemon = True
        thread.start()

    def onLogout(self, sessionID):
        with self.lock:
            self.subscribed = False
        self.logged_on.clear()
        log("MDCLIENT3 logged out; will subscribe again on the next logon")

    def toAdmin(self, message, sessionID):
        return

    def fromAdmin(self, message, sessionID):
        return

    def toApp(self, message, sessionID):
        return

    def fromApp(self, message, sessionID):
        if header_type(message) != "W":
            return
        try:
            symbol, entries = snapshot_entries(message)
            book = normalize(symbol, entries, datetime.now(timezone.utc))
        except RejectedSnapshot as error:
            log("rejected snapshot: {0}".format(error.reason))
            return
        except Exception as error:
            log("dropped snapshot: {0}".format(error))
            return
        self.accept(book)

    def accept(self, book):
        sequence = self.store.record(book)
        log(
            "stored {0} sequence={1} bids={2} asks={3} trades={4}".format(
                book["symbol"],
                sequence,
                len(book["bids"]),
                len(book["asks"]),
                len(book["trades"]),
            )
        )

    def _subscribe_after_logon(self, sessionID):
        # sendToTarget inside onLogon can deadlock QuickFIX.
        time.sleep(0.2)
        self.send_subscribe(sessionID)

    def send_subscribe(self, sessionID):
        with self.lock:
            if self.subscribed:
                return True
            sent = fix.Session.sendToTarget(
                market_data_request(self.symbols), sessionID
            )
            if sent:
                self.subscribed = True
                log("subscribed to {0}".format(",".join(self.symbols)))
            return sent


def main():
    symbols = load_symbols()
    host = os.environ.get("EXCHANGE_HOST", "127.0.0.1")
    config = render_config(host, dictionary_path())
    store = Store(database_url())
    application = Subscriber(symbols, store)
    settings = fix.SessionSettings(str(config))
    initiator = fix.SocketInitiator(
        application,
        fix.FileStoreFactory(settings),
        settings,
        fix.FileLogFactory(settings),
    )
    initiator.start()
    log("session started for {0}".format(",".join(symbols)))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("stopping")
    finally:
        initiator.stop()
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
