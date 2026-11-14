-- Client IP on audit rows. Safe to run again. Do not trust X-Forwarded-For yet.

ALTER TABLE audit_events
    ADD COLUMN IF NOT EXISTS client_ip TEXT;

INSERT INTO schema_migrations (filename)
VALUES ('009_audit_client_ip.sql')
ON CONFLICT (filename) DO NOTHING;
