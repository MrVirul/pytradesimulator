"""Optional layout and focus checks in a real browser.

Install the extra dependency and a browser to run this file:

    pip install -r secure_api/requirements-dev.txt
    python -m playwright install chromium

The rest of the suite does not need Playwright, and the Docker image does not
install it. Without the package or a browser these tests skip.
"""

import socket
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")

from playwright.sync_api import Error as PlaywrightError  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from secure_api.app.main import app  # noqa: E402

pytestmark = pytest.mark.browser

WIDTHS = (1440, 1280, 1024, 900, 800, 600, 400)

PAGES = (
    "/ui",
    "/ui/market",
    "/ui/alerts",
    "/ui/alerts/7",
    "/ui/security",
    "/ui/audit",
    "/ui/scenarios",
)


def _session(role="security_admin"):
    return {
        "client_id": role,
        "roles": [role],
        "access_token": "token",
        "csrf_token": "csrf-1",
        "id_token": "",
        "expires_at": None,
    }


def _free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture(scope="module")
def base_url(_context):
    import uvicorn

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 20
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "fixture server did not start"
    yield "http://127.0.0.1:{0}".format(port)
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        try:
            launched = playwright.chromium.launch()
        except PlaywrightError as error:
            pytest.skip("no Playwright browser is installed: {0}".format(error))
        yield launched
        launched.close()


@pytest.fixture(scope="module", autouse=True)
def _context():
    monkeypatch_module = pytest.MonkeyPatch()
    monkeypatch_module.setenv("RATE_LIMIT_REQUIRED", "0")
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.load_session", lambda session_id: _session()
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.decode_token",
        lambda token: {
            "roles": ["security_admin"],
            "client_id": "admin",
            "exp": 9999999999,
        },
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.feed_health",
        lambda: {"logged_on": True, "last_message_at": None},
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.list_books",
        lambda: [
            {
                "symbol": "BASELINE",
                "status": "stale",
                "received_at": "2026-10-23T00:00:00+00:00",
                "ingest_sequence": 6,
                "bids": [{"price": 10.0, "quantity": 1}],
                "asks": [{"price": 12.0, "quantity": 1}],
            }
        ],
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.snapshot",
        lambda subject, roles: [
            {"category": "market_data", "used": 2, "allowed": 60, "resets_at": None}
        ],
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.list_symbols",
        lambda: [
            {
                "symbol": "BASELINE",
                "status": "stale",
                "received_at": "2026-10-23T00:00:00+00:00",
            }
        ],
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.get_symbol",
        lambda symbol: {
            "symbol": symbol,
            "status": "stale",
            "received_at": "2026-10-23T00:00:00+00:00",
            "ingest_sequence": 6,
            "bids": [{"price": 51.0, "quantity": 10}],
            "asks": [{"price": 53.0, "quantity": 12}],
        },
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.recent_trades",
        lambda symbol, limit: [],
    )
    alerts = [
        {
            "id": index,
            "rule_name": "price_movement",
            "symbol": "BASELINE",
            "severity": "warning",
            "observed_value": 12.5,
            "threshold": 10.0,
            "created_at": "2026-10-23T00:00:00+00:00",
            "detail": "observed value crossed the threshold",
            "ingest_sequence": 6,
        }
        for index in range(1, 6)
    ]
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.list_alerts", lambda *args: alerts
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.get_alert", lambda alert_id: alerts[0]
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.alert_context",
        lambda found: {"book": None, "current_sequence": 9, "trades": []},
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.filter_choices",
        lambda: {
            "symbols": ["BASELINE"],
            "rules": ["price_movement"],
            "severities": ["warning"],
        },
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.list_rules",
        lambda: [
            {
                "name": "price_movement",
                "enabled": True,
                "threshold": 10.0,
                "window_seconds": 60,
            }
        ],
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.timeline", lambda: []
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.list_events",
        lambda *args: [
            {
                "request_id": "req-1",
                "client_id": "market",
                "action": "market-data:read",
                "resource": "/api/v1/market-data/BASELINE",
                "decision": "allowed",
                "reason": "ok",
                "status_code": 200,
                "latency_ms": 4,
                "recorded_at": "2026-10-23T00:00:00+00:00",
            }
        ],
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.security_metrics",
        lambda minutes: {
            "minutes": 15,
            "requests": 4,
            "allowed": 1,
            "denied": 3,
            "status_401": 0,
            "status_403": 1,
            "status_429": 2,
            "p50": 20.0,
            "p95": 40.0,
            "p99": 55.0,
            "per_minute": [
                {"minute": "2026-10-23T00:00:00+00:00", "count": 4, "width": 100}
            ],
            "clients": [{"client_id": "market", "count": 3}],
            "policies": [
                {
                    "subject": "*",
                    "category": "market_data",
                    "allowed": 60,
                    "used": 4,
                    "window_seconds": 60,
                }
            ],
        },
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.scenario_policy",
        lambda: {"requests_allowed": 3, "window_seconds": 60},
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.recent_runs", lambda limit=12: []
    )
    monkeypatch_module.setattr(
        "secure_api.app.web.routes.get_run", lambda run_id: None
    )
    yield
    monkeypatch_module.undo()


@pytest.fixture
def page(browser, base_url):
    context = browser.new_context()
    context.add_cookies(
        [
            {
                "name": "pytradesim_session",
                "value": "sess",
                "url": base_url,
            }
        ]
    )
    opened = context.new_page()
    opened.set_default_timeout(15000)
    yield opened
    context.close()


def _open(page, base_url, path):
    page.goto(base_url + path, wait_until="networkidle")
    return page.evaluate(
        """() => {
          const doc = document.documentElement;
          const main = document.querySelector('main');
          const bar = document.querySelector('.top');
          const outside = [];
          if (bar) {
            const bounds = bar.getBoundingClientRect();
            for (const child of bar.children) {
              const rect = child.getBoundingClientRect();
              if (rect.left < bounds.left - 1 || rect.right > bounds.right + 1 ||
                  rect.top < bounds.top - 1 || rect.bottom > bounds.bottom + 1) {
                outside.push(child.tagName + ' ' + (child.className || ''));
              }
            }
          }
          const controls = [];
          for (const filter of document.querySelectorAll('.filter-bar')) {
            const bounds = filter.getBoundingClientRect();
            for (const control of filter.querySelectorAll('label, input, select, button, a')) {
              const rect = control.getBoundingClientRect();
              if (rect.left < -1 || rect.right > window.innerWidth + 1 ||
                  rect.top < bounds.top - 1 || rect.bottom > bounds.bottom + 1) {
                controls.push(control.tagName + ' ' + (control.name || control.textContent || ''));
              }
            }
          }
          return {
            docOverflow: doc.scrollWidth - doc.clientWidth,
            mainOverflow: main ? main.scrollWidth - main.clientWidth : 0,
            outside: outside,
            controls: controls,
          };
        }"""
    )


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("path", PAGES)
def test_no_horizontal_overflow(browser, base_url, width, path):
    context = browser.new_context(viewport={"width": width, "height": 900})
    context.add_cookies(
        [
            {
                "name": "pytradesim_session",
                "value": "sess",
                "url": base_url,
            }
        ]
    )
    page = context.new_page()
    try:
        result = _open(page, base_url, path)
    finally:
        context.close()
    assert result["docOverflow"] <= 1, "{0} at {1}px: {2}".format(
        path, width, result
    )
    assert result["mainOverflow"] <= 1, "{0} at {1}px: {2}".format(
        path, width, result
    )
    assert not result["outside"], "{0} at {1}px: top bar children outside: {2}".format(
        path, width, result["outside"]
    )
    assert not result["controls"], "{0} at {1}px: filter controls outside: {2}".format(
        path, width, result["controls"]
    )


def test_poll_keeps_focus_on_the_third_alert(page, base_url):
    page.goto(base_url + "/ui/alerts?symbol=IGNORED", wait_until="networkidle")
    if page.locator("[data-row='alerts']").count() < 3:
        pytest.skip("fewer than three alert rows were rendered")
    page.locator("[data-row='alerts']").nth(2).focus()
    before = page.evaluate("() => document.activeElement.id")
    page.wait_for_function(
        """(previous) => {
          const active = document.activeElement;
          return active && active.id === previous && active.id !== '';
        }""",
        arg=before,
        timeout=15000,
    )
    page.wait_for_timeout(11000)
    after = page.evaluate("() => document.activeElement.id")
    assert after == before
