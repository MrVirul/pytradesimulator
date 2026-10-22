"""Read API. Authorization runs before any database call."""

import os
import threading
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from secure_api.app.auth import oidc
from secure_api.app.auth.jwt import TokenError, decode_token
from secure_api.app.auth.policies import allows
from secure_api.app.auth.rate_limit import consume
from secure_api.app.services.alerts import filter_error, list_alerts
from secure_api.app.services.audit import list_events, search_error, write_event
from secure_api.app.services.market_data import get_symbol, list_symbols, recent_trades
from secure_api.app.services.surveillance import watch_books
from secure_api.app.web.routes import router

app = FastAPI(
    title="pytradesim secure API",
    version="1",
    swagger_ui_init_oauth={
        "clientId": os.environ.get("KEYCLOAK_CLIENT_ID", "pytradesim-ui"),
        "scopes": "openid",
        "usePkceWithAuthorizationCodeGrant": True,
    },
)
app.include_router(router)
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "web", "static")),
    name="static",
)
_bearer = HTTPBearer(auto_error=False)


@app.on_event("startup")
def _start_surveillance():
    """Judge new books in this process. The subscriber does not write alerts."""
    if os.environ.get("SURVEILLANCE_ENABLED", "0") != "1":
        return
    if not os.environ.get("DATABASE_URL"):
        return
    threading.Thread(target=watch_books, name="surveillance", daemon=True).start()


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


@app.get("/api/v1/alerts")
def alerts(
    request: Request,
    symbol: str = "",
    severity: str = "",
    rule_name: str = "",
    _claims=Depends(require("alerts:read")),
):
    error = filter_error(symbol, severity, rule_name)
    if error:
        raise HTTPException(
            status_code=400,
            detail=error_body(error, "Invalid filter", request_id_of(request)),
        )
    if not os.environ.get("DATABASE_URL"):
        return {"alerts": []}
    return {"alerts": list_alerts(symbol, severity, rule_name)}


@app.get("/api/v1/audit-events")
def audit_events(
    request: Request,
    request_id: str = "",
    client_id: str = "",
    action: str = "",
    decision: str = "",
    status_code: str = "",
    recorded_from: str = "",
    recorded_to: str = "",
    _claims=Depends(require("audit:read")),
):
    error = search_error(
        request_id, client_id, action, decision, status_code, recorded_from, recorded_to
    )
    if error:
        raise HTTPException(
            status_code=400,
            detail=error_body(error, "Invalid filter", request_id_of(request)),
        )
    if not os.environ.get("DATABASE_URL"):
        return {"events": []}
    return {
        "events": list_events(
            request_id or None,
            client_id,
            action,
            decision,
            status_code or None,
            recorded_from,
            recorded_to,
        )
    }


def custom_openapi():
    """Serve Swagger from this process's routes, with Keycloak PKCE as a way to authorize."""
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi

    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    issuer = oidc.public_issuer()
    components = schema.setdefault("components", {})
    schemes = components.setdefault("securitySchemes", {})
    schemes["keycloak"] = {
        "type": "oauth2",
        "flows": {
            "authorizationCode": {
                "authorizationUrl": issuer + "/protocol/openid-connect/auth",
                "tokenUrl": issuer + "/protocol/openid-connect/token",
                "scopes": {"openid": "Identify the caller"},
            }
        },
    }
    for path, methods in schema.get("paths", {}).items():
        for method, operation in methods.items():
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            security = operation.get("security") or []
            if security:
                operation["security"] = security + [{"keycloak": ["openid"]}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
