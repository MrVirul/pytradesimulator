"""Rate-limit header helpers work without a database."""

from secure_api.app.auth.rate_limit import RateDecision
from secure_api.app.main import rate_limit_headers


def test_rate_limit_headers_from_decision():
    headers = rate_limit_headers(
        RateDecision(True, 0, limit=60, remaining=59, reset_seconds=42)
    )
    assert headers == {
        "X-RateLimit-Limit": "60",
        "X-RateLimit-Remaining": "59",
        "X-RateLimit-Reset": "42",
    }


def test_rate_limit_headers_omitted_when_unavailable():
    assert rate_limit_headers(RateDecision(False, 60, unavailable=True)) == {}
    assert rate_limit_headers(None) == {}
