"""JSON shapes published on the OpenAPI document."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorPayload(BaseModel):
    error: ErrorDetail

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": "Request limit exceeded",
                    "request_id": "req-example",
                }
            }
        }
    )


class HealthPayload(BaseModel):
    status: str = Field(examples=["ok"])


class SymbolSummary(BaseModel):
    symbol: str
    status: str
    received_at: str
    ingest_sequence: int
    exchange_event_time: Optional[str] = None


class MarketListPayload(BaseModel):
    symbols: List[SymbolSummary]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbols": [
                    {
                        "symbol": "BASELINE",
                        "status": "live",
                        "received_at": "2026-10-22T12:00:00+00:00",
                        "ingest_sequence": 6,
                        "exchange_event_time": None,
                    }
                ]
            }
        }
    )


class PriceLevel(BaseModel):
    price: float
    quantity: float


class BookPayload(BaseModel):
    symbol: str
    status: str
    received_at: str
    ingest_sequence: int
    exchange_event_time: Optional[str] = None
    bids: List[PriceLevel]
    asks: List[PriceLevel]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "BASELINE",
                "status": "live",
                "received_at": "2026-10-22T12:00:00+00:00",
                "ingest_sequence": 6,
                "exchange_event_time": None,
                "bids": [{"price": 51.0, "quantity": 40.0}],
                "asks": [],
            }
        }
    )


class TradePayload(BaseModel):
    ingestion_id: int
    price: float
    quantity: float
    received_at: str
    ingest_sequence: int


class TradeListPayload(BaseModel):
    symbol: str
    trades: List[TradePayload]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "BASELINE",
                "trades": [
                    {
                        "ingestion_id": 1,
                        "price": 189.0,
                        "quantity": 675.0,
                        "received_at": "2026-10-22T12:00:00+00:00",
                        "ingest_sequence": 6,
                    }
                ],
            }
        }
    )


class AlertPayload(BaseModel):
    id: int
    rule_name: str
    symbol: str
    severity: str
    observed_value: float
    threshold: float
    created_at: str
    detail: str


class AlertListPayload(BaseModel):
    alerts: List[AlertPayload]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "alerts": [
                    {
                        "id": 1,
                        "rule_name": "price_movement",
                        "symbol": "PRICE",
                        "severity": "warning",
                        "observed_value": 150.0,
                        "threshold": 100.0,
                        "created_at": "2026-10-22T12:00:00+00:00",
                        "detail": "price_movement observed 150.0 above 100",
                    }
                ]
            }
        }
    )


class AuditEventPayload(BaseModel):
    request_id: str
    client_id: str
    action: str
    resource: str
    decision: str
    reason: str
    status_code: int
    latency_ms: int
    recorded_at: str


class AuditListPayload(BaseModel):
    events: List[AuditEventPayload]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "events": [
                    {
                        "request_id": "req-example",
                        "client_id": "market",
                        "action": "market-data:read",
                        "resource": "/api/v1/market-data",
                        "decision": "allowed",
                        "reason": "ok",
                        "status_code": 200,
                        "latency_ms": 12,
                        "recorded_at": "2026-10-22T12:00:00+00:00",
                    }
                ]
            }
        }
    )


class ScenarioRequest(BaseModel):
    """Only the scenario name is accepted. Any other field is rejected."""

    model_config = ConfigDict(extra="allow")
    scenario: str = Field(
        examples=["price_movement"],
        description=(
            "price_movement, spread_widening, volume, "
            "unauthorized_access, or rate_limit_abuse"
        ),
    )


class ScenarioRunPayload(BaseModel):
    id: int
    scenario: str
    status: str
    symbol: str
    request_id: str


class ScenarioResponse(BaseModel):
    run: ScenarioRunPayload

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "run": {
                    "id": 1,
                    "scenario": "price_movement",
                    "status": "pending",
                    "symbol": "PRICE",
                    "request_id": "",
                }
            }
        }
    )
