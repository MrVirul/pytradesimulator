"""Read API. Authorization runs before any database call."""

import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from secure_api.app.auth.jwt import TokenError, decode_token
from secure_api.app.auth.policies import allows

app = FastAPI(title="pytradesim secure API", version="1")
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
        request.state.decision = "allowed"
        request.state.reason = "ok"
        return claims

    return dependency


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/market-data")
def market_data(_claims=Depends(require("market-data:read"))):
    return {"symbols": []}


@app.get("/api/v1/audit-events")
def audit_events(_claims=Depends(require("audit:read"))):
    return {"events": []}
