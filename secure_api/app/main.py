"""Read API. Authorization runs before any database call."""

import os
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from secure_api.app.auth.jwt import TokenError, decode_token
from secure_api.app.auth.policies import allows
from secure_api.app.auth.rate_limit import consume
from secure_api.app.services.audit import list_events, write_event
from secure_api.app.services.market_data import get_symbol, list_symbols, recent_trades
from secure_api.app.web.routes import router

app = FastAPI(title="pytradesim secure API", version="1")
app.include_router(router)
_bearer = HTTPBearer(auto_error=False)


@app.exception_handler(HTTPException)
def http_exception(request, exc):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(
            status_code=exc.status_code, content=exc.detail, headers=exc.headers
        )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body("error", str(exc.detail), request_id_of(request)),
        headers=exc.headers,
    )


def error_body(code, message, request_id):
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def request_id_of(request):
    current = getattr(request.state, "request_id", None)
    if current:
        return current
    incoming = request.headers.get("x-request-id")
    current = incoming or "req-{0}".format(uuid.uuid4().hex[:12])
    request.state.request_id = current
    return current


def require(permission):
    def dependency(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    ):
        request_id = request_id_of(request)
        request.state.action = permission
        request.state.resource = request.url.path
        request.state.client_id = "anonymous"
        request.state.decision = "denied"
        token = credentials.credentials if credentials is not None else ""
        try:
            claims = decode_token(token)
        except TokenError as error:
            request.state.reason = error.reason
            raise HTTPException(
                status_code=401,
                detail=error_body("unauthorized", "Invalid token", request_id),
            )
        request.state.client_id = claims["client_id"]
        if not allows(claims.get("roles"), permission):
            request.state.reason = "missing_scope"
            raise HTTPException(
                status_code=403,
                detail=error_body("forbidden", "Missing permission", request_id),
            )
        if os.environ.get("RATE_LIMIT_REQUIRED", "1") != "0":
            role = claims["roles"][0] if claims.get("roles") else ""
            decision = consume(claims["client_id"], role, permission)
            if not decision.allowed:
                request.state.decision = "denied"
                request.state.reason = (
                    "limiter_unavailable" if decision.unavailable else "rate_limited"
                )
                status = 503 if decision.unavailable else 429
                code = "unavailable" if decision.unavailable else "rate_limit_exceeded"
                headers = None
                if status == 429:
                    headers = {"Retry-After": str(decision.retry_after)}
                raise HTTPException(
                    status_code=status,
                    detail=error_body(code, "Request limit exceeded", request_id),
                    headers=headers,
                )
        request.state.decision = "allowed"
        request.state.reason = "ok"
        return claims

    return dependency


@app.middleware("http")
async def audit_request(request: Request, call_next):
    request_id_of(request)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        response = JSONResponse(
            status_code=500,
            content=error_body(
                "internal_error", "Internal error", request.state.request_id
            ),
        )
    response.headers["X-Request-ID"] = request.state.request_id
    if getattr(request.state, "action", None) and os.environ.get("DATABASE_URL"):
        try:
            write_event(
                {
                    "request_id": request.state.request_id,
                    "client_id": getattr(request.state, "client_id", "anonymous"),
                    "action": request.state.action,
                    "resource": getattr(request.state, "resource", request.url.path),
                    "decision": getattr(request.state, "decision", "denied"),
                    "reason": getattr(request.state, "reason", ""),
                    "status_code": response.status_code,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                }
            )
        except Exception:
            pass
    return response


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/market-data")
def market_data(_claims=Depends(require("market-data:read"))):
    if not os.environ.get("DATABASE_URL"):
        return {"symbols": []}
    return {"symbols": list_symbols()}


@app.get("/api/v1/market-data/{symbol}")
def market_data_symbol(symbol: str, request: Request, _claims=Depends(require("market-data:read"))):
    found = get_symbol(symbol)
    if found is None:
        raise HTTPException(
            status_code=404,
            detail=error_body("not_found", "Unknown symbol", request_id_of(request)),
        )
    return found


@app.get("/api/v1/market-data/{symbol}/trades")
def market_data_trades(
    symbol: str, request: Request, limit: int = 20, _claims=Depends(require("market-data:read"))
):
    found = recent_trades(symbol, limit)
    if found is None:
        raise HTTPException(
            status_code=400,
            detail=error_body("invalid_symbol", "Invalid symbol", request_id_of(request)),
        )
    return {"symbol": symbol, "trades": found}


@app.get("/api/v1/audit-events")
def audit_events(
    request: Request,
    request_id: str = "",
    _claims=Depends(require("audit:read")),
):
    return {"events": list_events(request_id or None)}
