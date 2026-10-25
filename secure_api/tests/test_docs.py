"""Swagger UI is the live OpenAPI document and can send a bearer token."""

from fastapi.testclient import TestClient

from secure_api.app.main import app


def test_docs_use_the_live_openapi_document():
    app.openapi_schema = None
    client = TestClient(app)
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    document = spec.json()
    flow = document["components"]["securitySchemes"]["keycloak"]["flows"]["authorizationCode"]
    assert flow["authorizationUrl"].endswith("/protocol/openid-connect/auth")
    assert flow["tokenUrl"].endswith("/protocol/openid-connect/token")
    market = document["paths"]["/api/v1/market-data"]["get"]["security"]
    assert {"keycloak": ["openid"]} in market
    assert document["paths"]["/api/v1/health"]["get"].get("security") in (None, [])
    book = document["components"]["schemas"]["BookPayload"]
    assert "bids" in book["properties"]
    assert book["example"]["symbol"] == "BASELINE"
    scenario = document["paths"]["/api/v1/scenarios"]["post"]
    body = scenario["requestBody"]["content"]["application/json"]
    assert body["examples"]["named"]["value"] == {"scenario": "price_movement"}
    assert "run" in document["components"]["schemas"]["ScenarioResponse"]["properties"]
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "swagger-ui" in docs.text
    assert "usePkceWithAuthorizationCodeGrant" in docs.text
    assert "/openapi.json" in docs.text
