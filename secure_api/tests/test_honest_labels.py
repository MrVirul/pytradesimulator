"""Filters name their time zone, list what is active, and failures say what next."""

from pathlib import Path

from fastapi.testclient import TestClient

from secure_api.app.main import app

WEB = Path(__file__).resolve().parents[1] / "app" / "web"


def _session(monkeypatch, role, client_id):
    monkeypatch.setenv("RATE_LIMIT_REQUIRED", "0")
    monkeypatch.setattr(
        "secure_api.app.web.routes.load_session",
        lambda session_id: {
            "client_id": client_id,
            "roles": [role],
            "access_token": "token",
            "csrf_token": "csrf",
            "id_token": "",
            "expires_at": None,
        },
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.decode_token",
        lambda token: {"roles": [role], "client_id": client_id, "exp": 9999999999},
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.feed_health",
        lambda: {"logged_on": False, "last_message_at": None},
    )


def _open_alerts(monkeypatch):
    _session(monkeypatch, "surveillance_analyst", "analyst")
    monkeypatch.setattr("secure_api.app.web.routes.list_alerts", lambda *a, **k: [])
    monkeypatch.setattr("secure_api.app.web.routes.list_rules", lambda: [])
    monkeypatch.setattr("secure_api.app.web.routes.timeline", lambda: [])
    monkeypatch.setattr(
        "secure_api.app.web.routes.filter_choices",
        lambda: {"symbols": ["BASELINE"], "rules": [], "severities": ["warning"]},
    )


def _open_audit(monkeypatch):
    _session(monkeypatch, "security_admin", "admin")
    monkeypatch.setattr("secure_api.app.web.routes.list_events", lambda *a, **k: [])
    monkeypatch.setattr(
        "secure_api.app.web.routes.security_metrics",
        lambda minutes: {
            "minutes": 15,
            "requests": 2,
            "allowed": 1,
            "denied": 1,
            "status_401": 0,
            "status_403": 1,
            "status_429": 0,
            "p50": 20.0,
            "p95": 40.0,
            "p99": 55.0,
            "per_minute": [],
            "clients": [],
            "policies": [],
        },
    )


def _get(path, params=None):
    return TestClient(app, base_url="https://testserver").get(
        path, params=params, headers={"Cookie": "pytradesim_session=sess"}
    )


def test_alert_filters_name_utc_and_list_the_active_values(monkeypatch):
    _open_alerts(monkeypatch)
    page = _get(
        "/ui/alerts",
        {
            "symbol": "BASELINE",
            "severity": "warning",
            "created_from": "2026-10-23T00:00",
            "created_to": "2026-10-24T00:00",
        },
    )
    assert page.status_code == 200
    text = page.text
    assert "From (UTC)" in text
    assert "To (UTC)" in text
    assert text.count('title="Times are UTC"') == 2
    assert "Time UTC" in text
    assert "Active filters:" in text
    assert "Symbol: BASELINE" in text
    assert "Severity: warning" in text
    assert "From: 2026-10-23T00:00 UTC" in text
    assert 'href="/ui/alerts">Clear</a>' in text
    rows = _get(
        "/ui/alerts/rows",
        {"symbol": "BASELINE", "severity": "warning"},
    )
    assert rows.status_code == 200
    assert "Symbol: BASELINE" in rows.text
    assert 'href="/ui/alerts">Clear</a>' in rows.text


def test_audit_filters_name_utc_and_list_the_active_values(monkeypatch):
    _open_audit(monkeypatch)
    page = _get("/ui/audit", {"request_id": "req-1", "status_code": "403"})
    assert page.status_code == 200
    text = page.text
    assert "From (UTC)" in text
    assert "To (UTC)" in text
    assert text.count('title="Times are UTC"') == 2
    assert "Time UTC" in text
    assert "Active filters:" in text
    assert "Request id: req-1" in text
    assert "Status: 403" in text
    assert 'href="/ui/audit">Clear</a>' in text
    assert "No audit events match this filter. Adjust or clear the filters." in text


def test_security_links_to_the_audit_log_instead_of_embedding_the_filter(monkeypatch):
    _open_audit(monkeypatch)
    page = _get("/ui/security")
    assert page.status_code == 200
    text = page.text
    assert "Open audit log" in text
    assert 'href="/ui/audit"' in text
    assert 'href="/ui/audit?status_code=403"' in text
    assert 'href="/ui/audit?status_code=429"' in text
    assert 'id="audit-filters"' not in text
    assert 'id="audit-rows"' not in text
    assert 'name="request_id"' not in text
    assert 'type="datetime-local"' not in text
    assert "Counts include console polling; each book refresh is one audited request." in text


def test_shortcuts_dialog_is_labelled_and_captions_describe_the_window():
    base = (WEB / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'aria-labelledby="shortcuts-title"' in base
    assert 'id="shortcuts-title"' in base

    scenarios = (WEB / "templates" / "scenarios.html").read_text(encoding="utf-8")
    assert "<caption>Last 12 runs, newest first</caption>" in scenarios
    alerts = (WEB / "templates" / "alerts.html").read_text(encoding="utf-8")
    assert "<caption>Rule thresholds in effect</caption>" in alerts
    assert "<caption>Recent alerts and scenario runs</caption>" in alerts
    security = (WEB / "templates" / "security.html").read_text(encoding="utf-8")
    assert "<caption>Top clients in this window</caption>" in security
    assert "<caption>Policies in effect</caption>" in security
    books = (WEB / "templates" / "overview_books.html").read_text(encoding="utf-8")
    assert "<caption>Books and their last change</caption>" in books

    css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
    assert "caption { text-align: left; }" in css


def test_error_page_is_bounded_and_offers_one_next_step():
    error = (WEB / "templates" / "error.html").read_text(encoding="utf-8")
    assert "error-card" in error
    assert 'href="/ui/login/start">Sign in again</a>' in error
    assert 'href="/ui/market">Back to Market</a>' in error
    assert 'href="/ui/market">Back</a>' in error
    assert 'title="Times are UTC"' not in error
    assert "Request " in error
    css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
    assert "max-width: 48ch" in css


def test_form_errors_have_a_visible_alert_target():
    alerts = (WEB / "templates" / "alerts.html").read_text(encoding="utf-8")
    audit = (WEB / "templates" / "audit_filters.html").read_text(encoding="utf-8")
    assert 'data-error="alert-filter-error"' in alerts
    assert 'id="alert-filter-error"' in alerts
    assert 'role="alert"' in alerts
    assert 'data-error="audit-filter-error"' in audit
    assert 'id="audit-filter-error"' in audit
    assert 'role="alert"' in audit
    script = (WEB / "static" / "console.js").read_text(encoding="utf-8")
    assert "htmx:responseError" in script
    assert "htmx:sendError" in script
    assert "Check the filter values" in script
    assert "Request failed, try again" in script
    assert "Missing permission" in script
    assert "Limit reached, retrying in" in script
