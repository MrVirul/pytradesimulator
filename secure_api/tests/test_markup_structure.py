"""Structural checks for every rendered page and fragment.

The M9.8 scan only looked for ``scope="col"`` inside each ``<th>``. A stray
``ead`` after the attribute still matched that pattern, so the malformed
``<th scope="col"ead>`` survived 15 templates. This test parses the same HTML a
browser would: table children, header structure, attribute names, unique ids,
and ``aria-labelledby`` targets.
"""

from html.parser import HTMLParser
import re

from fastapi.testclient import TestClient

from secure_api.app.main import app

VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}

KNOWN_ATTRS = {
    "abbr",
    "accept",
    "accept-charset",
    "accesskey",
    "action",
    "allow",
    "alt",
    "as",
    "async",
    "autocapitalize",
    "autocomplete",
    "autofocus",
    "autoplay",
    "charset",
    "checked",
    "cite",
    "class",
    "cols",
    "colspan",
    "content",
    "contenteditable",
    "controls",
    "coords",
    "crossorigin",
    "datetime",
    "decoding",
    "default",
    "defer",
    "dir",
    "dirname",
    "disabled",
    "download",
    "draggable",
    "enctype",
    "enterkeyhint",
    "fetchpriority",
    "for",
    "form",
    "formaction",
    "headers",
    "height",
    "hidden",
    "high",
    "href",
    "hreflang",
    "http-equiv",
    "id",
    "inputmode",
    "integrity",
    "ismap",
    "itemprop",
    "kind",
    "label",
    "lang",
    "list",
    "loading",
    "loop",
    "low",
    "max",
    "maxlength",
    "media",
    "method",
    "min",
    "minlength",
    "multiple",
    "muted",
    "name",
    "nonce",
    "novalidate",
    "open",
    "optimum",
    "pattern",
    "placeholder",
    "popover",
    "poster",
    "preload",
    "readonly",
    "referrerpolicy",
    "rel",
    "required",
    "reversed",
    "role",
    "rows",
    "rowspan",
    "sandbox",
    "scope",
    "selected",
    "shape",
    "size",
    "sizes",
    "slot",
    "span",
    "spellcheck",
    "src",
    "srcdoc",
    "srclang",
    "srcset",
    "start",
    "step",
    "style",
    "tabindex",
    "target",
    "title",
    "translate",
    "type",
    "usemap",
    "value",
    "width",
    "wrap",
}


def _allowed_attr(name):
    return (
        name in KNOWN_ATTRS
        or name.startswith("data-")
        or name.startswith("aria-")
        or name.startswith("hx-")
    )


class StructureParser(HTMLParser):
    def __init__(self, label):
        super().__init__(convert_charrefs=True)
        self.label = label
        self.stack = []
        self.tables = []
        self.ids = {}
        self.labelledby = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, closed=tag in VOID)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, closed=True)

    def _start(self, tag, attrs, closed):
        where = "{0} <{1}>".format(self.label, tag)
        names = []
        for name, value in attrs:
            if not _allowed_attr(name):
                self.errors.append("{0}: invalid attribute {1!r}".format(where, name))
            names.append((name, value))
        values = dict(names)
        if "id" in values:
            if values["id"] in self.ids:
                self.errors.append(
                    "{0}: duplicate id {1!r}".format(where, values["id"])
                )
            self.ids[values["id"]] = where
        if "aria-labelledby" in values:
            self.labelledby.append((values["aria-labelledby"], where))

        parent = self.stack[-1] if self.stack else None
        if parent == "table" and tag not in {
            "caption",
            "colgroup",
            "thead",
            "tbody",
            "tfoot",
        }:
            self.errors.append(
                "{0}: <{1}> is a direct child of <table>".format(where, tag)
            )

        if tag == "table":
            self.tables.append(
                {
                    "label": where,
                    "captions": 0,
                    "theads": 0,
                    "scoped_th": 0,
                }
            )
        elif tag == "caption" and parent == "table":
            self.tables[-1]["captions"] += 1
        elif tag == "thead" and parent == "table":
            self.tables[-1]["theads"] += 1
        elif (
            tag == "th"
            and "thead" in self.stack
            and values.get("scope") == "col"
        ):
            self.tables[-1]["scoped_th"] += 1

        if not closed:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if tag == "table" and self.tables:
            self._close_table()
        if tag in self.stack:
            while self.stack:
                open_tag = self.stack.pop()
                if open_tag == tag:
                    break

    def _close_table(self):
        table = self.tables.pop()
        if table["captions"] != 1:
            self.errors.append(
                "{0}: expected one <caption>, found {1}".format(
                    table["label"], table["captions"]
                )
            )
        if table["theads"] != 1:
            self.errors.append(
                "{0}: expected one <thead>, found {1}".format(
                    table["label"], table["theads"]
                )
            )
        if table["scoped_th"] < 1:
            self.errors.append(
                "{0}: no <th scope=\"col\"> inside <thead>".format(table["label"])
            )

    def finish(self):
        while self.tables:
            self._close_table()
        for ids, where in self.labelledby:
            for target in ids.split():
                if target not in self.ids:
                    self.errors.append(
                        "{0}: aria-labelledby target {1!r} does not exist".format(
                            where, target
                        )
                    )
        return self.errors


def _session(role):
    return {
        "client_id": role,
        "roles": [role],
        "access_token": "token",
        "csrf_token": "csrf-1",
        "id_token": "",
        "expires_at": None,
    }


def _open(monkeypatch, role="security_admin"):
    monkeypatch.setenv("RATE_LIMIT_REQUIRED", "0")
    monkeypatch.setattr(
        "secure_api.app.web.routes.load_session", lambda session_id: _session(role)
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.decode_token",
        lambda token: {"roles": [role], "client_id": role, "exp": 9999999999},
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.feed_health",
        lambda: {"logged_on": True, "last_message_at": None},
    )
    monkeypatch.setattr(
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
    monkeypatch.setattr(
        "secure_api.app.web.routes.snapshot",
        lambda subject, roles: [
            {"category": "market_data", "used": 2, "allowed": 60, "resets_at": None}
        ],
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.list_symbols",
        lambda: [
            {
                "symbol": "BASELINE",
                "status": "stale",
                "received_at": "2026-10-23T00:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(
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
    monkeypatch.setattr(
        "secure_api.app.web.routes.recent_trades",
        lambda symbol, limit: [
            {
                "ingestion_id": 1,
                "price": 51.0,
                "quantity": 10,
                "received_at": "2026-10-23T00:00:00+00:00",
                "ingest_sequence": 6,
            }
        ],
    )
    alert = {
        "id": 7,
        "rule_name": "price_movement",
        "symbol": "BASELINE",
        "severity": "warning",
        "observed_value": 12.5,
        "threshold": 10.0,
        "created_at": "2026-10-23T00:00:00+00:00",
        "detail": "observed value crossed the threshold",
        "ingest_sequence": 6,
    }
    monkeypatch.setattr("secure_api.app.web.routes.list_alerts", lambda *args: [alert])
    monkeypatch.setattr("secure_api.app.web.routes.get_alert", lambda alert_id: alert)
    monkeypatch.setattr(
        "secure_api.app.web.routes.alert_context",
        lambda found: {
            "book": None,
            "current_sequence": 9,
            "trades": [
                {
                    "ingestion_id": 1,
                    "price": 51.0,
                    "quantity": 10,
                    "received_at": "2026-10-23T00:00:00+00:00",
                }
            ],
        },
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.filter_choices",
        lambda: {"symbols": ["BASELINE"], "rules": ["price_movement"], "severities": ["warning"]},
    )
    monkeypatch.setattr(
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
    monkeypatch.setattr(
        "secure_api.app.web.routes.timeline",
        lambda: [
            {
                "at": "2026-10-23T00:00:00+00:00",
                "kind": "alert",
                "label": "price_movement",
                "ref": 7,
            }
        ],
    )
    monkeypatch.setattr(
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
    monkeypatch.setattr(
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
    monkeypatch.setattr(
        "secure_api.app.web.routes.scenario_policy",
        lambda: {"requests_allowed": 3, "window_seconds": 60},
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.recent_runs",
        lambda limit=12: [
            {
                "id": 4,
                "scenario": "price_movement",
                "status": "passed",
                "request_id": "req-run",
                "created_at": "2026-10-23T00:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(
        "secure_api.app.web.routes.get_run",
        lambda run_id: {
            "id": run_id,
            "scenario": "price_movement",
            "status": "running",
            "symbol": "PRICE",
            "request_id": "req-run",
        },
    )


def _pages(monkeypatch):
    _open(monkeypatch)
    client = TestClient(app, base_url="https://testserver")
    headers = {"Cookie": "pytradesim_session=sess"}
    targets = [
        ("/ui", "/ui"),
        ("/ui/overview/books", "/ui/overview/books"),
        ("/ui/market", "/ui/market"),
        ("/ui/market-data/BASELINE/book", "/ui/market-data/BASELINE/book"),
        ("/ui/alerts", "/ui/alerts"),
        ("/ui/alerts/rows", "/ui/alerts/rows"),
        ("/ui/alerts/7", "/ui/alerts/7"),
        ("/ui/security", "/ui/security"),
        ("/ui/audit", "/ui/audit"),
        ("/ui/audit/rows", "/ui/audit/rows"),
        ("/ui/scenarios", "/ui/scenarios"),
        ("/ui/scenarios/runs/4", "/ui/scenarios/runs/4"),
    ]
    pages = []
    for name, path in targets:
        response = client.get(path, headers=headers, follow_redirects=False)
        assert response.status_code == 200, "{0} returned {1}".format(
            name, response.status_code
        )
        pages.append((name, response.text))
    return pages


def test_pages_and_fragments_have_valid_structure(monkeypatch):
    failures = []
    for label, text in _pages(monkeypatch):
        errors = StructureParser(label)
        errors.feed(text)
        failures.extend(errors.finish())
    assert not failures, "\n".join(failures)


def test_login_page_has_valid_structure(monkeypatch):
    monkeypatch.setattr("secure_api.app.web.routes.load_session", lambda session_id: None)
    response = TestClient(app, base_url="https://testserver").get("/ui/login")
    assert response.status_code == 200
    errors = StructureParser("/ui/login")
    errors.feed(response.text)
    assert not errors.finish()


def test_error_page_has_valid_structure(monkeypatch):
    _open(monkeypatch, role="market_data_client")
    response = TestClient(app, base_url="https://testserver").get(
        "/ui/audit",
        headers={"Cookie": "pytradesim_session=sess"},
        follow_redirects=False,
    )
    assert response.status_code == 403
    errors = StructureParser("/ui/audit 403")
    errors.feed(response.text)
    assert not errors.finish()


def _attr(tag_text, name):
    found = re.search(r'\b{0}="([^"]*)"'.format(name), tag_text)
    return found.group(1) if found else ""


def test_polled_rows_and_controls_have_stable_ids(monkeypatch):
    prefixes = {
        "books": "books-",
        "alerts": "alert-",
        "audit": "audit-",
        "runs": "run-",
        "scenario": "scenario-",
        "watch": "watch-",
        "login": "login-",
    }
    failures = []
    for label, text in _pages(monkeypatch):
        for row in re.findall(r"<tr\b[^>]*data-row=\"[^\"]*\"[^>]*>", text, re.S):
            kind = _attr(row, "data-row")
            row_id = _attr(row, "id")
            prefix = prefixes.get(kind, kind)
            if not row_id.startswith(prefix):
                failures.append(
                    "{0}: {1} row has id {2!r}, expected {3}*".format(
                        label, kind, row_id, prefix
                    )
                )
        for button in re.findall(r"<button\b[^>]*data-copy=\"[^\"]*\"[^>]*>", text):
            if not _attr(button, "id"):
                failures.append("{0}: copy button has no id".format(label))
        for key in ("pause", "refresh"):
            pattern = r"<a\b[^>]*data-key=\"{0}\"[^>]*>".format(key)
            for control in re.findall(pattern, text):
                if not _attr(control, "id"):
                    failures.append(
                        "{0}: {1} control has no id".format(label, key)
                    )
    assert not failures, "\n".join(failures)

