"""Append-only audit writes. Callers must not pass tokens or cookies."""

from secure_api.app.db import connection, lock


def write_event(event):
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO audit_events (
                        request_id, client_id, action, resource,
                        decision, reason, status_code, latency_ms
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event["request_id"],
                        event["client_id"],
                        event["action"],
                        event["resource"],
                        event["decision"],
                        event["reason"],
                        event["status_code"],
                        event["latency_ms"],
                    ),
                )


def list_events(request_id):
    with lock():
        conn = connection()
        with conn.transaction():
            with conn.cursor() as cursor:
                if request_id:
                    cursor.execute(
                        """
                        SELECT request_id, client_id, action, resource,
                               decision, reason, status_code, latency_ms
                        FROM audit_events
                        WHERE request_id = %s
                        ORDER BY id DESC
                        LIMIT 50
                        """,
                        (request_id,),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT request_id, client_id, action, resource,
                               decision, reason, status_code, latency_ms
                        FROM audit_events
                        ORDER BY id DESC
                        LIMIT 50
                        """
                    )
                rows = cursor.fetchall()
    return [
        {
            "request_id": row[0],
            "client_id": row[1],
            "action": row[2],
            "resource": row[3],
            "decision": row[4],
            "reason": row[5],
            "status_code": row[6],
            "latency_ms": row[7],
        }
        for row in rows
    ]
