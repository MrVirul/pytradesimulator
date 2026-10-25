-- Server-side browser sessions. The cookie holds the session id, not the token.

CREATE TABLE IF NOT EXISTS oidc_attempts (
    state TEXT PRIMARY KEY,
    code_verifier TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS browser_sessions (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    roles JSONB NOT NULL,
    access_token TEXT NOT NULL,
    csrf_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, DELETE ON oidc_attempts TO pytradesim_app;
GRANT SELECT, INSERT, DELETE ON browser_sessions TO pytradesim_app;

INSERT INTO schema_migrations (filename)
VALUES ('003_browser_sessions.sql')
ON CONFLICT (filename) DO NOTHING;
