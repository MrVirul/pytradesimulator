-- Denial rules read audit_events. Safe to run again.

INSERT INTO surveillance_rules (name, enabled, threshold, window_seconds)
VALUES
    ('api_abuse', TRUE, 2, 60),
    ('access_denied', TRUE, 5, 60)
ON CONFLICT (name) DO NOTHING;

INSERT INTO schema_migrations (filename)
VALUES ('008_security_alerts.sql')
ON CONFLICT (filename) DO NOTHING;
