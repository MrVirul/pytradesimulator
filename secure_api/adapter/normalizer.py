"""Validate a FIX market-data snapshot before it is stored.

The input is the set of entries from one 35=W message. Prices and
quantities are checked here. Nothing in this module opens a socket or
trusts a message because it arrived on the Docker network.
"""

import math
import re


SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{1,16}$")
ENTRY_TYPES = {"0": "bids", "1": "asks", "2": "trades"}


class RejectedSnapshot(Exception):
    """A snapshot failed validation and must not be stored."""

    def __init__(self, reason):
        super(RejectedSnapshot, self).__init__(reason)
        self.reason = reason


def _require_number(value, reason):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise RejectedSnapshot(reason)
    if not math.isfinite(number) or number <= 0:
        raise RejectedSnapshot(reason)
    return number


def normalize(symbol, entries, received_at):
    """Return a validated book, or raise RejectedSnapshot.

    ``entries`` is a sequence of mappings with ``type``, ``price`` and
    ``quantity``. Entry type ``0`` is a bid, ``1`` an offer, ``2`` a trade.
    Identical trade prints are kept. ``exchange_event_time`` is always null
    because 35=W carries no trustworthy exchange timestamp.
    """
    if not isinstance(symbol, str) or SYMBOL_PATTERN.match(symbol) is None:
        raise RejectedSnapshot("invalid_symbol")
    if received_at is None:
        raise RejectedSnapshot("missing_received_at")
    if entries is None:
        raise RejectedSnapshot("missing_entries")

    book = {"bids": [], "asks": [], "trades": []}
    for entry in entries:
        if not isinstance(entry, dict):
            raise RejectedSnapshot("invalid_entry")
        entry_type = entry.get("type")
        if entry_type not in ENTRY_TYPES:
            raise RejectedSnapshot("invalid_entry_type")
        level = {
            "price": _require_number(entry.get("price"), "invalid_price"),
            "quantity": _require_number(entry.get("quantity"), "invalid_quantity"),
        }
        book[ENTRY_TYPES[entry_type]].append(level)

    return {
        "symbol": symbol,
        "received_at": received_at,
        "exchange_event_time": None,
        "status": "live",
        "bids": book["bids"],
        "asks": book["asks"],
        "trades": book["trades"],
    }
