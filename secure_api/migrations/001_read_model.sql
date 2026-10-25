-- Read model, audit store, and rate policies for the secure layer.
-- Applied by the Compose migrate service as the database owner.
-- Safe to run again: objects are created only when missing.

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE SEQUENCE IF NOT EXISTS ingest_sequence AS BIGINT;

CREATE TABLE IF NOT EXISTS market_snapshots (
    symbol TEXT PRIMARY KEY,
    received_at TIMESTAMPTZ NOT NULL,
    ingest_sequence BIGINT NOT NULL,
    exchange_event_time TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('live', 'stale', 'uninitialized')),
    bids JSONB NOT NULL,
    asks JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS market_observations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    symbol TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    ingest_sequence BIGINT NOT NULL UNIQUE,
    exchange_event_time TIMESTAMPTZ,
    bids JSONB NOT NULL,
    asks JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS market_observations_symbol_received_idx
    ON market_observations (symbol, received_at DESC);

CREATE TABLE IF NOT EXISTS trade_observations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    observation_id BIGINT NOT NULL REFERENCES market_observations (id),
    symbol TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    price NUMERIC NOT NULL CHECK (price > 0),
    quantity NUMERIC NOT NULL CHECK (quantity > 0),
    ingest_sequence BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS trade_observations_symbol_received_idx
    ON trade_observations (symbol, received_at DESC);

CREATE TABLE IF NOT EXISTS surveillance_rules (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    threshold NUMERIC NOT NULL,
    window_seconds INTEGER,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS surveillance_alerts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rule_id BIGINT NOT NULL REFERENCES surveillance_rules (id),
    symbol TEXT,
    severity TEXT NOT NULL,
    observed_value NUMERIC NOT NULL,
    threshold NUMERIC NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    detail TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    request_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT,
    status_code INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS audit_events_recorded_idx
    ON audit_events (recorded_at DESC);
CREATE INDEX IF NOT EXISTS audit_events_client_idx
    ON audit_events (client_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS audit_events_request_idx
    ON audit_events (request_id);

CREATE TABLE IF NOT EXISTS rate_limit_policies (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subject TEXT NOT NULL,
    category TEXT NOT NULL,
    requests_allowed INTEGER NOT NULL CHECK (requests_allowed > 0),
    window_seconds INTEGER NOT NULL CHECK (window_seconds > 0),
    UNIQUE (subject, category)
);

INSERT INTO rate_limit_policies (subject, category, requests_allowed, window_seconds)
VALUES
    ('*', 'market_data', 60, 60),
    ('*', 'alerts', 20, 60),
    ('*', 'audit', 10, 60),
    ('security_admin', 'scenario', 3, 60)
ON CONFLICT (subject, category) DO NOTHING;

CREATE TABLE IF NOT EXISTS feed_status (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    logged_on BOOLEAN NOT NULL,
    last_message_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL
);

INSERT INTO feed_status (id, logged_on, updated_at)
VALUES (1, FALSE, now())
ON CONFLICT (id) DO NOTHING;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pytradesim_app') THEN
        CREATE ROLE pytradesim_app LOGIN PASSWORD 'pytradesim';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE pytradesim TO pytradesim_app;
GRANT USAGE ON SCHEMA public TO pytradesim_app;
GRANT SELECT, INSERT, UPDATE ON
    market_snapshots,
    market_observations,
    trade_observations,
    surveillance_rules,
    surveillance_alerts,
    feed_status,
    rate_limit_policies
TO pytradesim_app;
GRANT SELECT, INSERT ON audit_events TO pytradesim_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO pytradesim_app;
GRANT USAGE, SELECT ON SEQUENCE ingest_sequence TO pytradesim_app;

INSERT INTO schema_migrations (filename)
VALUES ('001_read_model.sql')
ON CONFLICT (filename) DO NOTHING;
