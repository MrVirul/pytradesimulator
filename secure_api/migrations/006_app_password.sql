-- Align the app role password with the value Compose passed in.
-- A manual psql run that omits -v app_password leaves the password alone.

\if :{?app_password}
ALTER ROLE pytradesim_app PASSWORD :'app_password';
\endif

ALTER TABLE browser_sessions
    ADD COLUMN IF NOT EXISTS id_token TEXT NOT NULL DEFAULT '';

INSERT INTO schema_migrations (filename)
VALUES ('006_app_password.sql')
ON CONFLICT (filename) DO NOTHING;
