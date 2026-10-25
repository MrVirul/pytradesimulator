"""Server-side display formats. Templates do not format numbers themselves."""

from datetime import datetime, timezone


def _as_utc(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def price(value):
    if value is None or value == "":
        return "—"
    return "{:,.2f}".format(float(value))


def qty(value):
    if value is None or value == "":
        return "—"
    number = float(value)
    if number.is_integer():
        return "{:,.0f}".format(number)
    return "{:,.2f}".format(number)


def signed(value):
    if value is None or value == "":
        return "—"
    number = float(value)
    body = "{:,.2f}".format(abs(number))
    if number > 0:
        return "+" + body
    if number < 0:
        return "−" + body
    return body


def ts(value):
    parsed = _as_utc(value)
    if parsed is None:
        return "—"
    return parsed.strftime("%H:%M:%S.") + "{0:03d}".format(parsed.microsecond // 1000)


def tsd(value):
    parsed = _as_utc(value)
    if parsed is None:
        return "—"
    return parsed.strftime("%m-%d %H:%M:%S")


def age(seconds):
    if seconds is None or seconds == "":
        return "—"
    whole = max(0, int(seconds))
    if whole < 60:
        return "{0}s".format(whole)
    if whole < 3600:
        return "{0}:{1:02d}".format(whole // 60, whole % 60)
    return "{0}:{1:02d}:{2:02d}".format(whole // 3600, (whole % 3600) // 60, whole % 60)
