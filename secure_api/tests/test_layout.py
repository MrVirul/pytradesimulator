"""Every signed-in page shares a role-aware navigation bar."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from secure_api.app.main import app


def _client():
    return TestClient(app, base_url="https://testserver")


def _session(role):
    return {
        "client_id": role,
        "roles": [role],
        "access_token": "token",
        "csrf_token": "csrf-1",
        "id_token": "",
        "expires_at": None,
    }


def _open(monkeypatch, role):
    monkeypatch.setattr(
        "secure_api.app.web.routes._overview",
        lambda row: {
            "permissions": [],
            "feed": {"logged_on": False, "last_message_at": None},
            "symbols": [],
            "limits": [],
        },
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.load_session",
        lambda session_id: _session(role),
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.decode_token",
        lambda token: {"roles": [role], "client_id": role, "exp": 9999999999},
    )


def test_nav_matches_the_role(monkeypatch):
    expected = {
        "market_data_client": ["/ui", "/ui/market"],
        "surveillance_analyst": ["/ui", "/ui/market", "/ui/alerts"],
        "security_admin": ["/ui", "/ui/market", "/ui/alerts", "/ui/security", "/ui/scenarios"],
    }
    client = _client()
    for role, links in expected.items():
        _open(monkeypatch, role)
        response = client.get("/ui", headers={"Cookie": "pytradesim_session=sess"})
        assert response.status_code == 200
        assert "Sign out" in response.text
        assert 'name="csrf_token"' in response.text
        for href in ("/ui/alerts", "/ui/security", "/ui/scenarios"):
            marker = 'href="{0}"'.format(href)
            assert (marker in response.text) is (href in links)
        assert 'href="/docs"' in response.text
        assert 'id="poll-state"' in response.text
        assert 'id="feed-state"' in response.text
        assert 'src="/static/console.js"' in response.text
        assert 'name="viewport"' in response.text
        assert "data-server-now=" in response.text
        assert "localStorage" not in response.text
        assert 'href="#content"' in response.text
        assert "<header" in response.text and "<nav" in response.text and "<main" in response.text
        assert 'id="shortcuts"' in response.text
        assert 'id="shortcut-open"' in response.text
        assert 'aria-live="polite"' in response.text
        assert 'id="poll-announce"' in response.text
        assert 'role="status"' in response.text
        assert 'id="poll-state" data-tone="pending"' in response.text
        assert 'data-nav="1"' in response.text
        assert re.search(r'href="/ui"[^>]*aria-current="page"', response.text)


def test_nav_current_uses_path_prefixes():
    from secure_api.app.web.routes import nav_current

    assert nav_current("/ui", "/ui")
    assert not nav_current("/ui/alerts", "/ui")
    assert nav_current("/ui/alerts/120", "/ui/alerts")
    assert nav_current("/ui/market-data/BASELINE/book", "/ui/market")
    assert nav_current("/ui/market", "/ui/market")
    assert nav_current("/ui/audit", "/ui/security")
    assert nav_current("/ui/scenarios/runs/4", "/ui/scenarios")
    assert not nav_current("/ui/security", "/ui/alerts")
    assert not nav_current("/ui/scenarios", "/ui/security")


def test_nav_current_on_an_alert_detail(monkeypatch):
    _open(monkeypatch, "surveillance_analyst")
    monkeypatch.setenv("RATE_LIMIT_REQUIRED", "0")
    monkeypatch.setattr(
        "secure_api.app.web.routes.get_alert",
        lambda alert_id: {
            "id": 7,
            "rule_name": "spread_widening",
            "symbol": "SPREAD",
            "severity": "warning",
            "observed_value": 10.0,
            "threshold": 5.0,
            "created_at": "2026-10-23T00:00:00+00:00",
            "detail": "spread 10",
            "ingest_sequence": 3,
        },
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.alert_context",
        lambda alert: {"book": None, "current_sequence": 9, "trades": []},
    )
    response = _client().get(
        "/ui/alerts/7",
        headers={"Cookie": "pytradesim_session=sess"},
    )
    assert response.status_code == 200
    current = re.findall(
        r'href="([^"]+)"[^>]*aria-current="page"',
        response.text,
    )
    assert current == ["/ui/alerts"]


def test_tables_are_captioned_and_headers_are_scoped():
    root = Path(__file__).resolve().parents[1] / "app" / "web"
    book = (root / "templates" / "book.html").read_text(encoding="utf-8")
    assert "aria-live" not in book
    css = (root / "static" / "app.css").read_text(encoding="utf-8")
    assert "outline: 2px solid var(--focus)" in css
    assert "min-height: 24px" in css
    for path in (root / "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for header in re.findall(r"<th\b[^>]*>", text):
            assert 'scope="col"' in header
        assert text.count("<caption") >= text.count("<table")
        # The M9.8 version of this test only searched for scope="col" in the
        # opening tag, so "<th scope=\"col\"ead>" passed. Reject the malformed
        # attribute and require a real open and close for every header row.
        assert 'scope="col"ead' not in text
        if "<table" in text:
            assert "<thead" in text and "</thead>" in text
