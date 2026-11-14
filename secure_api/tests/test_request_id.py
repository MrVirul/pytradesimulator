"""Incoming X-Request-ID must match the audit token pattern."""

from fastapi.testclient import TestClient

from secure_api.app.main import app


def test_valid_request_id_is_echoed():
    client = TestClient(app)
    response = client.get(
        "/api/v1/health", headers={"X-Request-ID": "req-valid_ID-1"}
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-valid_ID-1"


def test_invalid_request_id_is_replaced():
    client = TestClient(app)
    too_long = "x" * 200
    response = client.get("/api/v1/health", headers={"X-Request-ID": too_long})
    assert response.status_code == 200
    echoed = response.headers["x-request-id"]
    assert echoed != too_long
    assert echoed.startswith("req-")
    assert len(echoed) <= 16

    dirty = client.get("/api/v1/health", headers={"X-Request-ID": "a b<c"})
    assert dirty.status_code == 200
    assert dirty.headers["x-request-id"] != "a b<c"
    assert dirty.headers["x-request-id"].startswith("req-")
