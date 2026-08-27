-- Local prototype authentication. Raw passwords and raw session tokens are never stored.
CREATE TABLE app_users (
  id text PRIMARY KEY,
  username text NOT NULL UNIQUE,
  password_hash text NOT NULL,
  role user_role NOT NULL,
  clinic_id text NOT NULL,
  clinician_kind text CHECK (clinician_kind IN ('doctor','nurse')),
  patient_id text REFERENCES patients(id) ON DELETE CASCADE,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((role = 'clinician' AND clinician_kind IS NOT NULL) OR (role <> 'clinician' AND clinician_kind IS NULL)),
  CHECK ((role = 'patient' AND patient_id IS NOT NULL) OR (role <> 'patient' AND patient_id IS NULL))
);

CREATE TABLE app_sessions (
  token_hash text PRIMARY KEY,
  user_id text NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX app_sessions_expiry_idx ON app_sessions(expires_at);
GRANT SELECT ON app_users TO nightingale_app;
GRANT SELECT,INSERT,DELETE ON app_sessions TO nightingale_app;
