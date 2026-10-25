-- Per-client rate limit counters. Policies live in rate_limit_policies.

CREATE TABLE IF NOT EXISTS rate_limit_counters (
    subject TEXT NOT NULL,
    category TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL CHECK (request_count >= 0),
    PRIMARY KEY (subject, category)
);

GRANT SELECT, INSERT, UPDATE ON rate_limit_counters TO pytradesim_app;

INSERT INTO schema_migrations (filename)
VALUES ('002_rate_limits.sql')
ON CONFLICT (filename) DO NOTHING;
