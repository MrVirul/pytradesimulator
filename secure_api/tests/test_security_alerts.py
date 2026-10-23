"""Repeated 429s for one client become a single api_abuse alert."""

import os
import uuid

import psycopg
import pytest

from secure_api.app.services.alerts import list_alerts
from secure_api.app.services.surveillance import evaluate_pending


def test_three_rate_limits_produce_one_api_abuse_alert():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL is not set")
    client_id = "abuse-{0}".format(uuid.uuid4().hex[:8])
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        with conn.cursor() as cursor:
            for _index in range(3):
                cursor.execute(
                    """
                    INSERT INTO audit_events (
                        request_id, client_id, action, resource,
                        decision, reason, status_code, latency_ms
                    )
                    VALUES (%s, %s, 'market-data:read', '/api/v1/market-data/BASELINE',
                            'denied', 'rate_limited', 429, 5)
                    """,
                    ("req-{0}".format(uuid.uuid4().hex[:12]), client_id),
                )
        conn.commit()
    evaluate_pending()
    evaluate_pending()
    found = [
        alert
        for alert in list_alerts("", "", "api_abuse")
        if client_id in (alert["detail"] or "")
    ]
    assert len(found) == 1
    assert found[0]["symbol"] is None
    assert found[0]["observed_value"] >= 3
