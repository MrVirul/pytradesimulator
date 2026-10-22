"""Browser session. Cookies carry a session id. Tokens stay in the database."""

import os
import secrets

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

router = APIRouter()
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)


def _error(code, message, request):
    request_id = getattr(request.state, "request_id", "")
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def _secure_cookie():
    return os.environ.get("COOKIE_SECURE", "1") != "0"


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


def _open_session(request):
    request.state.action = "market-data:read"
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
    if not allows(claims.get("roles"), "market-data:read"):
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
