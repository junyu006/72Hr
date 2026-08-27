-- Local-development PostgreSQL bootstrap for Nightingale.
-- Run this file while connected as the PostgreSQL administrator (normally
-- "postgres" on Windows, or the account that installed PostgreSQL on macOS).
-- This password is intentionally only for the local demonstration environment.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nightingale_app') THEN
    CREATE ROLE nightingale_app LOGIN PASSWORD 'nightingale_local';
  ELSE
    ALTER ROLE nightingale_app LOGIN PASSWORD 'nightingale_local';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE nightingale TO nightingale_app;
GRANT USAGE ON SCHEMA public TO nightingale_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO nightingale_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO nightingale_app;

-- Ensure every table and sequence created by the migration user is usable by
-- the application role. PostgreSQL RLS policies still enforce authorization.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO nightingale_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO nightingale_app;
