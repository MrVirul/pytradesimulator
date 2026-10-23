"""Browser session. Cookies carry a session id. Tokens stay in the database."""

import asyncio
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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
    list_symbols,
    recent_trades,
)

router = APIRouter()
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)

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
    return {
        "signed_in": signed_in,
        "client_id": row.get("client_id", "") if signed_in else "",
        "roles": roles,
        "csrf_token": row.get("csrf_token", "") if signed_in else "",
        "minutes_left": minutes,
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


def render_error(request, status, message):
    hx = request.headers.get("hx-request", "").lower() == "true"
    name = "error_fragment.html" if hx else "error.html"
    context = {"title": "Request failed", "message": message}
    if hx:
        return templates.TemplateResponse(request, name, context, status_code=status)
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
    id_token = ""
    session_id = request.cookies.get(SESSION_COOKIE)
    row = load_session(session_id)
    if row:
        id_token = row.get("id_token") or ""
        delete_session(session_id)
    return RedirectResponse(
        logout_url(public_api_url() + "/ui/login/resume", user, id_token),
        status_code=302,
    )


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
        return HTMLResponse(
            "<h1>This account cannot open the app</h1>"
            '<p><a href="/ui/login">Back to sign in</a></p>',
            status_code=403,
        )
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


def _overview(row):
    tiles = []
    for item in list_symbols():
        book = get_symbol(item["symbol"]) or {}
        tiles.append(
            {
                "symbol": item["symbol"],
                "status": item["status"],
                "age_seconds": _age_seconds(item["received_at"]),
                "best_bid": _best(book.get("bids") or [], max),
                "best_ask": _best(book.get("asks") or [], min),
            }
        )
    return {
        "permissions": _permissions(row.get("roles")),
        "feed": feed_health(),
        "symbols": tiles,
        "limits": snapshot(row.get("client_id"), row.get("roles")),
    }


@router.get("/ui", response_class=HTMLResponse)
def home(request: Request):
    row = _open_session(request)
    if row is None:
        return _login_redirect(request)
    return page(request, "home.html", row, _overview(row))


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


def _book_context(symbol):
    book = get_symbol(symbol)
    trades = recent_trades(symbol, 20) or []
    health = feed_health()
    if book is None:
        return {
            "symbol": symbol,
            "status": "uninitialized",
            "received_at": None,
            "age_seconds": None,
            "ingest_sequence": None,
            "bids": [],
            "asks": [],
            "trades": [],
            "logged_on": health["logged_on"],
            "best_bid": None,
            "best_ask": None,
            "spread": None,
            "last_trade": None,
        }
    bids = book["bids"]
    asks = book["asks"]
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
        "trades": trades,
        "logged_on": health["logged_on"],
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "last_trade": trades[0] if trades else None,
    }


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
        items.append({"symbol": symbol, "status": "uninitialized"})
    context = _book_context(symbol)
    context["symbol_choices"] = choices
    context["symbols"] = items
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
    return templates.TemplateResponse(request, "book.html", context)


def _alert_filters(symbol, severity, rule_name, request, created_from="", created_to=""):
    error = filter_error(symbol, severity, rule_name, created_from, created_to)
    if error:
        raise HTTPException(
            status_code=400,
            detail=_error(error, "Invalid filter", request),
        )
    return {
        "alerts": list_alerts(symbol, severity, rule_name, created_from, created_to),
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
    return page(
        request,
        "alert_detail.html",
        request.state.session_row,
        {"alert": found, "stored": alert_context(found)},
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
    for item in snapshot(row.get("client_id"), row.get("roles")):
        if item["category"] == "scenario":
            remaining = item["allowed"] - item["used"]
    return {
        "scenarios": scenario_choices(),
        "policy": scenario_policy(),
        "csrf_token": row["csrf_token"],
        "run": run,
        "history": history,
        "last_status": last,
        "remaining": remaining,
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
        "events": list_events(
            request_id or None,
            client_id,
            action,
            decision,
            status_code or None,
            recorded_from,
            recorded_to,
        ),
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
    context["report"] = security_metrics(minutes)
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
