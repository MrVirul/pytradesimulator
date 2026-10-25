-- Price, spread, and volume rules. The API writes one alert per crossing.
-- Safe to run again.

ALTER TABLE surveillance_alerts
    ADD COLUMN IF NOT EXISTS ingest_sequence BIGINT;

CREATE UNIQUE INDEX IF NOT EXISTS surveillance_alerts_rule_symbol_sequence
    ON surveillance_alerts (rule_id, symbol, ingest_sequence);

CREATE TABLE IF NOT EXISTS surveillance_checkpoints (
    symbol TEXT PRIMARY KEY,
    ingest_sequence BIGINT NOT NULL
);

GRANT SELECT, INSERT, UPDATE ON surveillance_checkpoints TO pytradesim_app;

INSERT INTO surveillance_rules (name, enabled, threshold, window_seconds)
VALUES
    ('price_movement', TRUE, 100, NULL),
    ('spread_widening', TRUE, 5, NULL),
    ('volume', TRUE, 1000, 60)
ON CONFLICT (name) DO NOTHING;

INSERT INTO schema_migrations (filename)
VALUES ('004_surveillance_rules.sql')
ON CONFLICT (filename) DO NOTHING;
