"""Browser session. Cookies carry a session id. Tokens stay in the database."""

import asyncio
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from secure_api.app.auth.browser import (
    DEMO_USERS,
    SESSION_COOKIE,
    delete_session,
    load_session,
    new_attempt,
    save_session,
    take_attempt,
)
from secure_api.app.auth.jwt import TokenError, decode_token
from secure_api.app.auth.oidc import authorize_url, exchange_code, logout_url
from secure_api.app.config import demo_users, public_api_url, show_demo_credentials
from secure_api.app.auth.policies import ROLE_PERMISSIONS, allows
from secure_api.app.auth.rate_limit import consume, snapshot
from secure_api.app.services.alerts import (
    alert_context,
    filter_choices,
    filter_error,
    get_alert,
    list_alerts,
    list_rules,
    timeline,
    update_rule,
)
from secure_api.app.services.audit import list_events, search_error, security_metrics
from secure_api.app.services.scenarios import (
    get_run,
    recent_runs,
    scenario_choices,
    scenario_policy,
    start_named,
)
from secure_api.harness.scenarios import ScenarioError, parse_request
from secure_api.app.services.market_data import (
    SYMBOL_PATTERN,
    feed_health,
    get_symbol,
    list_books,
    list_symbols,
    recent_trades,
)
from secure_api.app.web.format import age as format_age
from secure_api.app.web.format import price as format_price
from secure_api.app.web.format import qty as format_qty
from secure_api.app.web.format import signed as format_signed
from secure_api.app.web.format import ts as format_ts
from secure_api.app.web.format import tsd as format_tsd

router = APIRouter()
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)
templates.env.filters["price"] = format_price
templates.env.filters["qty"] = format_qty
templates.env.filters["signed"] = format_signed
templates.env.filters["ts"] = format_ts
templates.env.filters["tsd"] = format_tsd
templates.env.filters["age"] = format_age

NAV = (
    ("Overview", "/ui", "market-data:read"),
    ("Market", "/ui/market", "market-data:read"),
    ("Surveillance", "/ui/alerts", "alerts:read"),
    ("Security", "/ui/security", "audit:read"),
    ("Scenarios", "/ui/scenarios", "scenarios:run"),
)


def shell(row, request):
    minutes = 0
    signed_in = row is not None
    roles = list(row.get("roles") or []) if signed_in else []
    expires = row.get("expires_at") if signed_in else None
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        minutes = max(0, int((expires - datetime.now(timezone.utc)).total_seconds() // 60))
    visible = []
    for label, href, permission in NAV:
        if signed_in and allows(roles, permission):
            visible.append((label, href))
    feed = {"logged_on": False, "last_message_at": None}
    if os.environ.get("DATABASE_URL"):
        try:
            feed = feed_health()
        except Exception:
            feed = {"logged_on": False, "last_message_at": None}
    return {
        "signed_in": signed_in,
        "client_id": row.get("client_id", "") if signed_in else "",
        "roles": roles,
        "csrf_token": row.get("csrf_token", "") if signed_in else "",
        "minutes_left": minutes,
        "expires_at": expires.isoformat() if expires is not None else "",
        "server_now": datetime.now(timezone.utc).isoformat(),
        "feed": feed,
        "nav": visible,
        "path": request.url.path,
    }


def page(request, name, row, extra, status_code=200):
    context = shell(row, request)
    context.update(extra)
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def _error(code, message, request):
    request_id = getattr(request.state, "request_id", "")
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def _viewer_can_audit(request):
    if not os.environ.get("DATABASE_URL"):
        return False
    try:
        row = load_session(request.cookies.get(SESSION_COOKIE))
        if not row:
            return False
        claims = decode_token(row["access_token"])
    except Exception:
        return False
    return allows(claims.get("roles"), "audit:read")


def render_error(request, status, message):
    hx = request.headers.get("hx-request", "").lower() == "true"
    name = "error_fragment.html" if hx else "error.html"
    context = {
        "title": "Request failed",
        "message": message,
        "status": status,
        "request_id": getattr(request.state, "request_id", "") or "",
        "can_audit": False,
    }
    if hx:
        return templates.TemplateResponse(request, name, context, status_code=status)
    context["can_audit"] = _viewer_can_audit(request)
    context.update(shell(None, request))
    return templates.TemplateResponse(request, name, context, status_code=status)


def _login_redirect(request):
    target = "/ui/login?error=expired"
    if request.headers.get("hx-request", "").lower() == "true":
        return HTMLResponse("", status_code=200, headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=302)


def _fragment_id(request):
    path = request.url.path
    if path.startswith("/ui/alerts"):
        return "alert-rows"
    if path.startswith("/ui/audit"):
        return "audit-rows"
    if path.startswith("/ui/scenarios"):
        return "scenario-run"
    return "market-book"


def _limit_response(request, retry_after):
    retry = max(1, int(retry_after or 60))
    if request.headers.get("hx-request", "").lower() != "true":
        response = render_error(request, 429, "Limit reached, retrying in {0} s".format(retry))
        response.headers["Retry-After"] = str(retry)
        return response
    target = request.url.path
    if request.url.query:
        target = target + "?" + request.url.query
    body = (
        '<section id="{0}" hx-get="{1}" hx-trigger="every {2}s" hx-swap="outerHTML">'
        "<p>Limit reached, retrying in {2} s</p></section>"
    ).format(_fragment_id(request), target, retry)
    return HTMLResponse(body, status_code=429, headers={"Retry-After": str(retry)})


def _secure_cookie():
    from secure_api.app.config import cookie_secure

    return cookie_secure()


def _set_session_cookie(response, session_id):
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        secure=_secure_cookie(),
        samesite="lax",
        path="/",
    )


@router.get("/ui/login", response_class=HTMLResponse)
def login_page(request: Request):
    if os.environ.get("DATABASE_URL") and load_session(request.cookies.get(SESSION_COOKIE)):
        return RedirectResponse("/ui", status_code=302)
    return page(
        request,
        "login.html",
        None,
        {
            "error": request.query_params.get("error", ""),
            "notice": request.query_params.get("state", ""),
            "users": demo_users(),
            "show_passwords": show_demo_credentials(),
        },
    )


@router.get("/ui/login/start")
def login_start(request: Request, user: str = ""):
    if not os.environ.get("DATABASE_URL"):
        raise HTTPException(
            status_code=503,
            detail=_error("unavailable", "Sign-in is unavailable", request),
        )
    if user and user not in DEMO_USERS:
        return RedirectResponse("/ui/login?error=unknown_user", status_code=302)
    if not user:
        state, verifier = new_attempt()
        return RedirectResponse(authorize_url(state, verifier), status_code=302)
    session_id = request.cookies.get(SESSION_COOKIE)
    row = load_session(session_id)
    id_token = row.get("id_token") if row else ""
    if row:
        delete_session(session_id)
    if id_token:
        return RedirectResponse(
            logout_url(public_api_url() + "/ui/login/resume", user, id_token),
            status_code=302,
        )
    state, verifier = new_attempt()
    return RedirectResponse(authorize_url(state, verifier, user), status_code=302)


@router.get("/ui/login/resume")
def login_resume(request: Request, state: str = ""):
    if not os.environ.get("DATABASE_URL"):
        raise HTTPException(
            status_code=503,
            detail=_error("unavailable", "Sign-in is unavailable", request),
        )
    user = state if state in DEMO_USERS else ""
    if state and state not in DEMO_USERS:
        return RedirectResponse("/ui/login?error=unknown_user", status_code=302)
    attempt_state, verifier = new_attempt()
    return RedirectResponse(authorize_url(attempt_state, verifier, user), status_code=302)


@router.get("/ui/callback")
def callback(request: Request, code: str = "", state: str = ""):
    request.state.action = "market-data:read"
    request.state.resource = "/ui/callback"
    request.state.client_id = "anonymous"
    request.state.decision = "denied"
    verifier = take_attempt(state) if state else None
    if not verifier or not code:
        request.state.reason = "invalid_login"
        return RedirectResponse("/ui/login?error=expired", status_code=302)
    try:
        exchanged = exchange_code(verifier, code)
        if isinstance(exchanged, str):
            access_token, id_token = exchanged, ""
        else:
            access_token = exchanged["access_token"]
            id_token = exchanged.get("id_token") or ""
        claims = decode_token(access_token)
    except (RuntimeError, TokenError, KeyError, TypeError):
        request.state.reason = "invalid_login"
        return RedirectResponse("/ui/login?error=failed", status_code=302)
    if not allows(claims.get("roles"), "market-data:read"):
        request.state.client_id = claims["client_id"]
        request.state.reason = "missing_scope"
        return render_error(request, 403, "This account cannot open the app")
    session_id, _csrf = save_session(claims, access_token, id_token)
    request.state.client_id = claims["client_id"]
    request.state.decision = "allowed"
    request.state.reason = "ok"
    response = RedirectResponse("/ui", status_code=303)
    _set_session_cookie(response, session_id)
    return response


def _open_session(request, permission="market-data:read"):
    request.state.action = permission
    request.state.resource = request.url.path
    request.state.client_id = "anonymous"
    request.state.decision = "denied"
    row = load_session(request.cookies.get(SESSION_COOKIE))
    if row is None:
        return None
    try:
        claims = decode_token(row["access_token"])
    except TokenError:
        request.state.reason = "expired"
        return None
    request.state.client_id = claims["client_id"]
    if not allows(claims.get("roles"), permission):
        request.state.reason = "missing_scope"
        raise HTTPException(
            status_code=403,
            detail=_error("forbidden", "Missing permission", request),
        )
    request.state.decision = "allowed"
    request.state.reason = "ok"
    request.state.session_row = row
    return row


def _permissions(roles):
    granted = []
    for role in roles or []:
        for permission in sorted(ROLE_PERMISSIONS.get(role, ())):
            if permission not in granted:
                granted.append(permission)
    return granted


def _best(levels, pick):
    if not levels:
        return None
    return pick(level["price"] for level in levels)


def _tiles():
    rows = []
    for book in list_books():
        bid = _best(book["bids"], max)
        ask = _best(book["asks"], min)
        spread = None
        if bid is not None and ask is not None:
            spread = ask - bid
        rows.append(
            {
                "symbol": book["symbol"],
                "status": book["status"],
                "received_at": book["received_at"],
                "age_seconds": _age_seconds(book["received_at"]),
                "ingest_sequence": book["ingest_sequence"],
                "best_bid": bid,
                "best_ask": ask,
                "spread": spread,
            }
        )
    return rows


def _limit_rows(limits):
    rows = []
    for item in limits:
        allowed = int(item["allowed"])
        used = int(item["used"])
        if allowed > 0 and used >= allowed:
            tone = "deny"
        elif allowed > 0 and used * 10 >= allowed * 7:
            tone = "warn"
        else:
            tone = "ok"
        fill = 0 if allowed <= 0 else min(100, int(round(100.0 * used / allowed)))
        copied = dict(item)
        copied["tone"] = tone
        copied["fill"] = fill
        rows.append(copied)
    return rows


def _overview(row):
    return {
        "permissions": _permissions(row.get("roles")),
        "feed": feed_health(),
        "symbols": _tiles(),
        "limits": _limit_rows(snapshot(row.get("client_id"), row.get("roles"))),
    }


@router.get("/ui", response_class=HTMLResponse)
def home(request: Request):
    row = _open_session(request)
    if row is None:
        return _login_redirect(request)
    return page(request, "home.html", row, _overview(row))


@router.get("/ui/overview/books", response_class=HTMLResponse)
def overview_books(request: Request):
    blocked = _market_guard(request)
    if blocked is not None:
        return blocked
    return templates.TemplateResponse(request, "overview_books.html", {"symbols": _tiles()})


@router.post("/ui/logout")
def logout(request: Request, csrf_token: str = Form("")):
    request.state.action = "market-data:read"
    request.state.resource = "/ui/logout"
    request.state.client_id = "anonymous"
    request.state.decision = "denied"
    session_id = request.cookies.get(SESSION_COOKIE, "")
    row = load_session(session_id)
    if row is None or not secrets.compare_digest(row["csrf_token"], csrf_token or ""):
        request.state.reason = "invalid_csrf"
        raise HTTPException(
            status_code=403,
            detail=_error("forbidden", "Missing permission", request),
        )
    delete_session(session_id)
    request.state.client_id = row["client_id"]
    request.state.decision = "allowed"
    request.state.reason = "ok"
    response = RedirectResponse(
        logout_url(public_api_url() + "/ui/login", "signed_out", row.get("id_token") or ""),
        status_code=303,
    )
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


def _age_seconds(received_at):
    if not received_at:
        return None
    parsed = datetime.fromisoformat(received_at)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    elapsed = datetime.now(timezone.utc) - parsed
    return max(0, int(elapsed.total_seconds()))


def _ladder(levels, inside_first):
    """Highest price first. Cumulative size grows from the inside of the book outward."""
    ordered = sorted(levels or [], key=lambda level: float(level["price"]), reverse=True)
    walk = list(ordered) if inside_first else list(reversed(ordered))
    running = 0.0
    cumulative = {}
    for level in walk:
        running += float(level["quantity"])
        cumulative[id(level)] = running
    return [
        {
            "price": level["price"],
            "quantity": level["quantity"],
            "cumulative": cumulative[id(level)],
        }
        for level in ordered
    ]


def _tape(trades):
    rows = []
    for index, trade in enumerate(trades):
        older = trades[index + 1] if index + 1 < len(trades) else None
        tick = "flat"
        if older is not None:
            if trade["price"] > older["price"]:
                tick = "up"
            elif trade["price"] < older["price"]:
                tick = "down"
        copied = dict(trade)
        copied["tick"] = tick
        rows.append(copied)
    return rows


def _book_context(symbol):
    book = get_symbol(symbol)
    trades = _tape(recent_trades(symbol, 20) or [])
    health = feed_health()
    now = datetime.now(timezone.utc).isoformat()
    if book is None:
        return {
            "symbol": symbol,
            "status": "uninitialized",
            "received_at": None,
            "age_seconds": None,
            "ingest_sequence": None,
            "bids": [],
            "asks": [],
            "max_qty": 1,
            "trades": trades,
            "logged_on": health["logged_on"],
            "best_bid": None,
            "best_ask": None,
            "spread": None,
            "last_trade": trades[0] if trades else None,
            "server_now": now,
        }
    bids = _ladder(book["bids"], inside_first=True)
    asks = _ladder(book["asks"], inside_first=False)
    sizes = [level["quantity"] for level in bids + asks]
    best_bid = _best(bids, max)
    best_ask = _best(asks, min)
    spread = None
    if best_bid is not None and best_ask is not None:
        spread = best_ask - best_bid
    return {
        "symbol": book["symbol"],
        "status": book["status"],
        "received_at": book["received_at"],
        "age_seconds": _age_seconds(book["received_at"]),
        "ingest_sequence": book["ingest_sequence"],
        "bids": bids,
        "asks": asks,
        "max_qty": max(sizes) if sizes else 1,
        "trades": trades,
        "logged_on": health["logged_on"],
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "last_trade": trades[0] if trades else None,
        "server_now": now,
    }


def _book_unchanged(request, context):
    since = request.query_params.get("since")
    status = request.query_params.get("st")
    logged = request.query_params.get("lo")
    if since is None or status is None or logged is None:
        return False
    sequence = context["ingest_sequence"]
    same_sequence = since == ("" if sequence is None else str(sequence))
    same_feed = logged == ("1" if context["logged_on"] else "0")
    return same_sequence and status == context["status"] and same_feed


def _market_guard(request):
    return _guard(request, "market-data:read")


def _guard(request, permission):
    row = _open_session(request, permission)
    if row is None:
        return _login_redirect(request)
    if os.environ.get("RATE_LIMIT_REQUIRED", "1") == "0":
        return None
    role = row["roles"][0] if row.get("roles") else ""
    decision = consume(row["client_id"], role, permission)
    if decision.allowed:
        return None
    request.state.decision = "denied"
    request.state.reason = (
        "limiter_unavailable" if decision.unavailable else "rate_limited"
    )
    if decision.unavailable:
        return render_error(request, 503, "The rate limiter is unavailable")
    return _limit_response(request, decision.retry_after)


@router.get("/ui/market", response_class=HTMLResponse)
def market_page(request: Request, symbol: str = "BASELINE"):
    blocked = _market_guard(request)
    if blocked is not None:
        return blocked
    if SYMBOL_PATTERN.match(symbol or "") is None:
        raise HTTPException(
            status_code=400,
            detail=_error("invalid_symbol", "Invalid symbol", request),
        )
    items = list_symbols()
    choices = [item["symbol"] for item in items]
    if symbol not in choices:
        choices.append(symbol)
        items.append({"symbol": symbol, "status": "uninitialized", "received_at": None})
    for item in items:
        item["age_seconds"] = _age_seconds(item.get("received_at"))
    context = _book_context(symbol)
    context["symbol_choices"] = choices
    context["symbols"] = items
    index = choices.index(symbol) if symbol in choices else -1
    context["previous_symbol"] = choices[index - 1] if index > 0 else ""
    context["next_symbol"] = choices[index + 1] if index >= 0 and index + 1 < len(choices) else ""
    return page(request, "market.html", request.state.session_row, context)


@router.get("/ui/market-data/{symbol}/book", response_class=HTMLResponse)
def market_book(request: Request, symbol: str):
    blocked = _market_guard(request)
    if blocked is not None:
        return blocked
    if SYMBOL_PATTERN.match(symbol or "") is None:
        raise HTTPException(
            status_code=400,
            detail=_error("invalid_symbol", "Invalid symbol", request),
        )
    context = _book_context(symbol)
    context["paused"] = request.query_params.get("paused") == "1"
    context["fragment"] = True
    if not context["paused"] and _book_unchanged(request, context):
        return Response(status_code=204)
    return templates.TemplateResponse(request, "book.html", context)


_AUDIT_STATUS = {"api_abuse": 429, "access_denied": 403}


def _with_excess(alert):
    copied = dict(alert)
    observed = alert.get("observed_value")
    threshold = alert.get("threshold")
    excess = None
    ratio_label = None
    threshold_pct = None
    observed_pct = None
    if observed is not None and threshold is not None:
        observed = float(observed)
        threshold = float(threshold)
        excess = observed - threshold
        if threshold != 0:
            ratio_label = "{0:.2f}×".format(observed / threshold)
        top = max(observed, threshold, 0.0)
        scale = top * 1.1 if top > 0 else 1.0
        threshold_pct = threshold / scale * 100.0
        observed_pct = observed / scale * 100.0
    copied["excess"] = excess
    copied["ratio_label"] = ratio_label
    copied["threshold_pct"] = threshold_pct
    copied["observed_pct"] = observed_pct
    return copied


def _ladder_view(book):
    if not book:
        return None
    bids = _ladder(book.get("bids"), inside_first=True)
    asks = _ladder(book.get("asks"), inside_first=False)
    sizes = [level["quantity"] for level in bids + asks]
    best_bid = _best(bids, max)
    best_ask = _best(asks, min)
    spread = None
    if best_bid is not None and best_ask is not None:
        spread = best_ask - best_bid
    return {
        "bids": bids,
        "asks": asks,
        "max_qty": max(sizes) if sizes else 1,
        "spread": spread,
    }


def _alert_filters(symbol, severity, rule_name, request, created_from="", created_to=""):
    error = filter_error(symbol, severity, rule_name, created_from, created_to)
    if error:
        raise HTTPException(
            status_code=400,
            detail=_error(error, "Invalid filter", request),
        )
    return {
        "alerts": [_with_excess(item) for item in list_alerts(symbol, severity, rule_name, created_from, created_to)],
        "symbol": symbol,
        "severity": severity,
        "rule_name": rule_name,
        "created_from": created_from,
        "created_to": created_to,
    }


@router.get("/ui/alerts", response_class=HTMLResponse)
def alerts_page(
    request: Request,
    symbol: str = "",
    severity: str = "",
    rule_name: str = "",
    created_from: str = "",
    created_to: str = "",
):
    blocked = _guard(request, "alerts:read")
    if blocked is not None:
        return blocked
    context = _alert_filters(symbol, severity, rule_name, request, created_from, created_to)
    row = request.state.session_row
    context["choices"] = filter_choices()
    context["rules"] = list_rules()
    context["events"] = timeline()
    context["can_write_rules"] = allows(row.get("roles"), "rules:write")
    return page(request, "alerts.html", row, context)


@router.get("/ui/alerts/rows", response_class=HTMLResponse)
def alert_rows(
    request: Request,
    symbol: str = "",
    severity: str = "",
    rule_name: str = "",
    created_from: str = "",
    created_to: str = "",
):
    blocked = _guard(request, "alerts:read")
    if blocked is not None:
        return blocked
    context = _alert_filters(symbol, severity, rule_name, request, created_from, created_to)
    return templates.TemplateResponse(request, "alert_rows.html", context)


@router.get("/ui/alerts/{alert_id}", response_class=HTMLResponse)
def alert_page(request: Request, alert_id: int):
    blocked = _guard(request, "alerts:read")
    if blocked is not None:
        return blocked
    found = get_alert(alert_id)
    if found is None:
        raise HTTPException(status_code=404, detail=_error("not_found", "Alert not found", request))
    stored = alert_context(found)
    audit_status = None
    if found.get("symbol") is None and found.get("ingest_sequence") is None:
        audit_status = _AUDIT_STATUS.get(found.get("rule_name"))
    return page(
        request,
        "alert_detail.html",
        request.state.session_row,
        {
            "alert": _with_excess(found),
            "stored": stored,
            "ladder": None if audit_status else _ladder_view(stored.get("book")),
            "audit_status": audit_status,
        },
    )


@router.post("/ui/rules")
def change_rule(
    request: Request,
    csrf_token: str = Form(""),
    name: str = Form(""),
    threshold: str = Form(""),
    enabled: str = Form(""),
):
    blocked = _guard(request, "rules:write")
    if blocked is not None:
        return blocked
    row = request.state.session_row
    if not secrets.compare_digest(row["csrf_token"], csrf_token or ""):
        request.state.decision = "denied"
        request.state.reason = "invalid_csrf"
        raise HTTPException(status_code=403, detail=_error("forbidden", "Missing permission", request))
    try:
        value = float(threshold)
    except ValueError:
        value = 0
    if value <= 0 or not update_rule(name, value, enabled == "1"):
        raise HTTPException(status_code=400, detail=_error("invalid_rule", "Invalid rule", request))
    request.state.reason = "administrative_change"
    return RedirectResponse("/ui/alerts", status_code=303)


def _scenario_page_context(row, run_id):
    run = get_run(run_id) if run_id else None
    history = recent_runs()
    last = {}
    for item in history:
        if item["scenario"] not in last:
            last[item["scenario"]] = item["status"]
    remaining = None
    resets_at = None
    budget = None
    for item in snapshot(row.get("client_id"), row.get("roles")):
        if item["category"] == "scenario":
            remaining = int(item["allowed"]) - int(item["used"])
            resets_at = item.get("resets_at")
            budget = _limit_rows([item])[0]
    return {
        "scenarios": scenario_choices(),
        "policy": scenario_policy(),
        "csrf_token": row["csrf_token"],
        "run": run,
        "history": history,
        "last_status": last,
        "remaining": remaining,
        "resets_at": resets_at,
        "budget": budget,
    }


def _limit_scenario(request, row):
    if os.environ.get("RATE_LIMIT_REQUIRED", "1") == "0":
        return None
    role = row["roles"][0] if row.get("roles") else ""
    decision = consume(row["client_id"], role, "scenarios:run")
    if decision.allowed:
        return None
    request.state.decision = "denied"
    request.state.reason = (
        "limiter_unavailable" if decision.unavailable else "rate_limited"
    )
    if decision.unavailable:
        return render_error(request, 503, "The rate limiter is unavailable")
    return _limit_response(request, decision.retry_after)


@router.get("/ui/scenarios", response_class=HTMLResponse)
def scenarios_page(request: Request, run: int = 0):
    row = _open_session(request, "scenarios:run")
    if row is None:
        return _login_redirect(request)
    return page(request, "scenarios.html", row, _scenario_page_context(row, run))


@router.get("/ui/scenarios/runs/{run_id}", response_class=HTMLResponse)
def scenario_run(request: Request, run_id: int):
    row = _open_session(request, "scenarios:run")
    if row is None:
        return _login_redirect(request)
    found = get_run(run_id)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail=_error("not_found", "Unknown scenario run", request),
        )
    return templates.TemplateResponse(
        request, "scenario_run.html", {"run": found, "csrf_token": row["csrf_token"]}
    )


@router.post("/ui/scenarios")
async def start_scenario(request: Request):
    row = _open_session(request, "scenarios:run")
    if row is None:
        return _login_redirect(request)
    form = await request.form()
    supplied = str(form.get("csrf_token") or "")
    if not supplied or not secrets.compare_digest(row["csrf_token"], supplied):
        request.state.decision = "denied"
        request.state.reason = "invalid_csrf"
        raise HTTPException(
            status_code=403,
            detail=_error("forbidden", "Missing permission", request),
        )
    limited = _limit_scenario(request, row)
    if limited is not None:
        return limited
    payload = {}
    for key in form.keys():
        if key == "csrf_token":
            continue
        payload[key] = form.get(key)
    try:
        name = parse_request(payload)
    except ScenarioError as error:
        request.state.decision = "denied"
        request.state.reason = error.reason
        raise HTTPException(
            status_code=400,
            detail=_error(error.reason, "Invalid scenario", request),
        )
    run = await asyncio.to_thread(start_named, name, row["client_id"])
    return RedirectResponse(
        "/ui/scenarios?run={0}".format(run["id"]), status_code=303
    )


def _clock(value):
    if not value:
        return "—"
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return str(value)
    return parsed.strftime("%H:%M")


def _event_view(event):
    copied = dict(event)
    decision = copied.get("decision")
    if decision == "allowed":
        copied["decision_tone"] = "ok"
    elif decision == "denied":
        copied["decision_tone"] = "denied"
    else:
        copied["decision_tone"] = ""
    code = copied.get("status_code")
    tone = ""
    bold = False
    if code not in (None, ""):
        number = int(code)
        if 200 <= number < 300:
            tone = "ok"
        elif number in (401, 403):
            tone = "denied"
        elif number == 429:
            tone = "warning"
        elif number >= 500:
            tone = "denied"
            bold = True
    copied["status_tone"] = tone
    copied["status_bold"] = bold
    return copied


def _count_tone(value, hot):
    if not value:
        return "muted"
    return hot


def _security_view(report):
    copied = dict(report)
    requests = int(copied.get("requests") or 0)
    clients = []
    for client in copied.get("clients") or []:
        item = dict(client)
        count = int(item.get("count") or 0)
        item["share"] = 0 if requests <= 0 else min(100, int(round(100.0 * count / requests)))
        clients.append(item)
    copied["clients"] = clients
    minutes = []
    for bar in copied.get("per_minute") or []:
        item = dict(bar)
        item["label"] = _clock(item.get("minute"))
        minutes.append(item)
    copied["per_minute"] = minutes
    copied["policies"] = _limit_rows(copied.get("policies") or [])
    copied["tone_401"] = _count_tone(copied.get("status_401"), "deny")
    copied["tone_403"] = _count_tone(copied.get("status_403"), "deny")
    copied["tone_429"] = _count_tone(copied.get("status_429"), "warn")
    return copied


def _audit_context(request, request_id, client_id, action, decision, status_code, recorded_from, recorded_to):
    error = search_error(
        request_id, client_id, action, decision, status_code, recorded_from, recorded_to
    )
    if error:
        raise HTTPException(
            status_code=400,
            detail=_error(error, "Invalid filter", request),
        )
    return {
        "events": [
            _event_view(event)
            for event in list_events(
                request_id or None,
                client_id,
                action,
                decision,
                status_code or None,
                recorded_from,
                recorded_to,
            )
        ],
        "request_id": request_id,
        "client_id": client_id,
        "action": action,
        "decision": decision,
        "status_code": status_code,
        "recorded_from": recorded_from,
        "recorded_to": recorded_to,
    }


@router.get("/ui/security", response_class=HTMLResponse)
def security_page(request: Request, minutes: int = 15):
    blocked = _guard(request, "audit:read")
    if blocked is not None:
        return blocked
    context = _audit_context(request, "", "", "", "", "", "", "")
    context["filter_client"] = context.pop("client_id")
    context["report"] = _security_view(security_metrics(minutes))
    context["as_of"] = datetime.now(timezone.utc).strftime("%H:%M:%S")
    return page(request, "security.html", request.state.session_row, context)


@router.get("/ui/audit", response_class=HTMLResponse)
def audit_page(
    request: Request,
    request_id: str = "",
    client_id: str = "",
    action: str = "",
    decision: str = "",
    status_code: str = "",
    recorded_from: str = "",
    recorded_to: str = "",
):
    blocked = _guard(request, "audit:read")
    if blocked is not None:
        return blocked
    context = _audit_context(
        request, request_id, client_id, action, decision, status_code, recorded_from, recorded_to
    )
    context["filter_client"] = context.pop("client_id")
    return page(request, "audit.html", request.state.session_row, context)


@router.get("/ui/audit/rows", response_class=HTMLResponse)
def audit_rows(
    request: Request,
    request_id: str = "",
    client_id: str = "",
    action: str = "",
    decision: str = "",
    status_code: str = "",
    recorded_from: str = "",
    recorded_to: str = "",
):
    blocked = _guard(request, "audit:read")
    if blocked is not None:
        return blocked
    context = _audit_context(
        request, request_id, client_id, action, decision, status_code, recorded_from, recorded_to
    )
    return templates.TemplateResponse(request, "audit_rows.html", context)
