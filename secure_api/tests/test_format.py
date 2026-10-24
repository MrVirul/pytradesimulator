"""Display filters keep numeric columns stable."""

from datetime import datetime, timezone

from secure_api.app.web.format import age, price, qty, signed, ts, tsd


def test_numbers_and_timestamps():
    assert price(None) == "—"
    assert price(189) == "189.00"
    assert price(1234.5) == "1,234.50"
    assert qty(10) == "10"
    assert qty(10.5) == "10.50"
    assert signed(1.2) == "+1.20"
    assert signed(-1.2) == "−1.20"
    assert signed(0) == "0.00"
    moment = datetime(2026, 10, 24, 6, 7, 8, 9000, tzinfo=timezone.utc)
    assert ts(moment) == "06:07:08.009"
    assert tsd(moment) == "10-24 06:07:08"
    assert age(None) == "—"
    assert age(9) == "9s"
    assert age(61) == "1:01"
    assert age(3661) == "1:01:01"
