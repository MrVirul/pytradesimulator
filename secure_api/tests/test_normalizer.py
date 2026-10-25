from datetime import datetime, timezone

import pytest

from secure_api.adapter.normalizer import RejectedSnapshot, normalize


RECEIVED = datetime(2026, 10, 22, 8, 30, 15, tzinfo=timezone.utc)


def test_valid_snapshot_keeps_each_trade():
    result = normalize(
        "MSFT",
        [
            {"type": "0", "price": 189, "quantity": 675},
            {"type": "1", "price": "190.5", "quantity": "10"},
            {"type": "2", "price": 189, "quantity": 100},
            {"type": "2", "price": 189, "quantity": 100},
        ],
        RECEIVED,
    )

    assert result["symbol"] == "MSFT"
    assert result["received_at"] == RECEIVED
    assert result["exchange_event_time"] is None
    assert result["status"] == "live"
    assert result["bids"] == [{"price": 189.0, "quantity": 675.0}]
    assert result["asks"] == [{"price": 190.5, "quantity": 10.0}]
    assert result["trades"] == [
        {"price": 189.0, "quantity": 100.0},
        {"price": 189.0, "quantity": 100.0},
    ]


def test_empty_book_is_valid():
    result = normalize("HYG", [], RECEIVED)

    assert result["bids"] == []
    assert result["asks"] == []
    assert result["trades"] == []


@pytest.mark.parametrize(
    "symbol,entries,reason",
    [
        ("msft", [], "invalid_symbol"),
        ("", [], "invalid_symbol"),
        ("TOO_LONG_SYMBOL_OK", [], "invalid_symbol"),
        ("MSFT", None, "missing_entries"),
        ("MSFT", [{"type": "3", "price": 1, "quantity": 1}], "invalid_entry_type"),
        ("MSFT", ["bid"], "invalid_entry"),
        ("MSFT", [{"type": "0", "price": 0, "quantity": 1}], "invalid_price"),
        ("MSFT", [{"type": "0", "price": -1, "quantity": 1}], "invalid_price"),
        ("MSFT", [{"type": "0", "price": "nan", "quantity": 1}], "invalid_price"),
        ("MSFT", [{"type": "1", "price": 1, "quantity": 0}], "invalid_quantity"),
        ("MSFT", [{"type": "2", "price": 1, "quantity": "x"}], "invalid_quantity"),
    ],
)
def test_rejects_invalid_fields(symbol, entries, reason):
    with pytest.raises(RejectedSnapshot) as caught:
        normalize(symbol, entries, RECEIVED)
    assert caught.value.reason == reason


def test_rejects_missing_receive_time():
    with pytest.raises(RejectedSnapshot) as caught:
        normalize("MSFT", [], None)
    assert caught.value.reason == "missing_received_at"
