-- Admin changes have their own limit. Safe to run again.

INSERT INTO rate_limit_policies (subject, category, requests_allowed, window_seconds)
VALUES ('*', 'admin', 20, 60)
ON CONFLICT (subject, category) DO NOTHING;

INSERT INTO schema_migrations (filename)
VALUES ('007_admin_rate.sql')
ON CONFLICT (filename) DO NOTHING;
