"""Browser session. Cookies carry a session id. Tokens stay in the database."""

import asyncio
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from secure_api.app.auth.browser import (
    SESSION_COOKIE,
    delete_session,
    load_session,
    new_attempt,
    save_session,
    take_attempt,
)
from secure_api.app.auth.jwt import TokenError, decode_token
from secure_api.app.auth.oidc import authorize_url, exchange_code
from secure_api.app.auth.policies import allows
from secure_api.app.auth.rate_limit import consume
from secure_api.app.services.alerts import filter_error, list_alerts
from secure_api.app.services.audit import list_events, search_error
from secure_api.app.services.scenarios import (
    get_run,
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


def _error(code, message, request):
    request_id = getattr(request.state, "request_id", "")
    return {"error": {"code": code, "message": message, "request_id": request_id}}


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
    return templates.TemplateResponse(request, "login.html")


@router.get("/ui/login/start")
def login_start(request: Request):
    if not os.environ.get("DATABASE_URL"):
        raise HTTPException(
            status_code=503,
            detail=_error("unavailable", "Sign-in is unavailable", request),
        )
    state, verifier = new_attempt()
    return RedirectResponse(authorize_url(state, verifier), status_code=302)


@router.get("/ui/callback")
def callback(request: Request, code: str = "", state: str = ""):
    request.state.action = "market-data:read"
    request.state.resource = "/ui/callback"
    request.state.client_id = "anonymous"
    request.state.decision = "denied"
    verifier = take_attempt(state) if state else None
    if not verifier or not code:
        request.state.reason = "invalid_login"
        raise HTTPException(
            status_code=400,
            detail=_error("invalid_login", "Sign-in could not be completed", request),
        )
    try:
        access_token = exchange_code(verifier, code)
        claims = decode_token(access_token)
    except (RuntimeError, TokenError):
        request.state.reason = "invalid_login"
        raise HTTPException(
            status_code=401,
            detail=_error("unauthorized", "Sign-in could not be completed", request),
        )
    if not allows(claims.get("roles"), "market-data:read"):
        request.state.client_id = claims["client_id"]
        request.state.reason = "missing_scope"
        raise HTTPException(
            status_code=403,
            detail=_error("forbidden", "Missing permission", request),
        )
    session_id, _csrf = save_session(claims, access_token)
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
    return row


@router.get("/ui", response_class=HTMLResponse)
def home(request: Request):
    row = _open_session(request)
    if row is None:
        return RedirectResponse("/ui/login", status_code=302)
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "client_id": row["client_id"],
            "roles": ", ".join(row["roles"] or []),
            "csrf_token": row["csrf_token"],
            "can_read_alerts": allows(row["roles"], "alerts:read"),
            "can_read_audit": allows(row["roles"], "audit:read"),
            "can_run_scenarios": allows(row["roles"], "scenarios:run"),
        },
    )


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
    response = RedirectResponse("/ui/login", status_code=303)
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
        }
    return {
        "symbol": book["symbol"],
        "status": book["status"],
        "received_at": book["received_at"],
        "age_seconds": _age_seconds(book["received_at"]),
        "ingest_sequence": book["ingest_sequence"],
        "bids": book["bids"],
        "asks": book["asks"],
        "trades": trades,
        "logged_on": health["logged_on"],
    }


def _market_guard(request):
    return _guard(request, "market-data:read")


def _guard(request, permission):
    row = _open_session(request, permission)
    if row is None:
        return RedirectResponse("/ui/login", status_code=302)
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
    status = 503 if decision.unavailable else 429
    headers = None
    if status == 429:
        headers = {"Retry-After": str(decision.retry_after)}
    return HTMLResponse(
        '<section id="market-book"><p>Request limit exceeded</p></section>',
        status_code=status,
        headers=headers,
    )


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
    choices = [item["symbol"] for item in list_symbols()]
    if symbol not in choices:
        choices.append(symbol)
    context = _book_context(symbol)
    context["symbol_choices"] = choices
    return templates.TemplateResponse(request, "market.html", context)


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
    return templates.TemplateResponse(request, "book.html", _book_context(symbol))


def _alert_filters(symbol, severity, rule_name, request):
    error = filter_error(symbol, severity, rule_name)
    if error:
        raise HTTPException(
            status_code=400,
            detail=_error(error, "Invalid filter", request),
        )
    return {
        "alerts": list_alerts(symbol, severity, rule_name),
        "symbol": symbol,
        "severity": severity,
        "rule_name": rule_name,
    }


@router.get("/ui/alerts", response_class=HTMLResponse)
def alerts_page(
    request: Request, symbol: str = "", severity: str = "", rule_name: str = ""
):
    blocked = _guard(request, "alerts:read")
    if blocked is not None:
        return blocked
    context = _alert_filters(symbol, severity, rule_name, request)
    return templates.TemplateResponse(request, "alerts.html", context)


@router.get("/ui/alerts/rows", response_class=HTMLResponse)
def alert_rows(
    request: Request, symbol: str = "", severity: str = "", rule_name: str = ""
):
    blocked = _guard(request, "alerts:read")
    if blocked is not None:
        return blocked
    context = _alert_filters(symbol, severity, rule_name, request)
    return templates.TemplateResponse(request, "alert_rows.html", context)


def _scenario_page_context(row, run_id):
    run = get_run(run_id) if run_id else None
    return {
        "scenarios": scenario_choices(),
        "policy": scenario_policy(),
        "csrf_token": row["csrf_token"],
        "run": run,
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
    status = 503 if decision.unavailable else 429
    headers = None
    if status == 429:
        headers = {"Retry-After": str(decision.retry_after)}
    return HTMLResponse(
        '<section id="scenario-run"><p>Request limit exceeded</p></section>',
        status_code=status,
        headers=headers,
    )


@router.get("/ui/scenarios", response_class=HTMLResponse)
def scenarios_page(request: Request, run: int = 0):
    row = _open_session(request, "scenarios:run")
    if row is None:
        return RedirectResponse("/ui/login", status_code=302)
    return templates.TemplateResponse(
        request, "scenarios.html", _scenario_page_context(row, run)
    )


@router.get("/ui/scenarios/runs/{run_id}", response_class=HTMLResponse)
def scenario_run(request: Request, run_id: int):
    row = _open_session(request, "scenarios:run")
    if row is None:
        return RedirectResponse("/ui/login", status_code=302)
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
        return RedirectResponse("/ui/login", status_code=302)
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
    return templates.TemplateResponse(request, "audit.html", context)


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
