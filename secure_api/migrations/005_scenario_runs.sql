-- Named scenario runs. The API inserts a name. The worker sends the fixed orders.
-- Safe to run again.

CREATE TABLE IF NOT EXISTS scenario_runs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scenario_name TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'passed', 'failed')),
    detail TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

GRANT SELECT, INSERT, UPDATE ON scenario_runs TO pytradesim_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO pytradesim_app;

INSERT INTO schema_migrations (filename)
VALUES ('005_scenario_runs.sql')
ON CONFLICT (filename) DO NOTHING;
