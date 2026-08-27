-- Nightingale core schema. Execute with a non-application database owner.
CREATE TYPE user_role AS ENUM ('patient', 'staff', 'clinician', 'admin', 'system');
CREATE TYPE entry_section AS ENUM ('staff_notes', 'clinician_sections', 'patient_facing', 'ai_scribed');

CREATE TABLE patients (
  id text PRIMARY KEY, clinic_id text NOT NULL, display_label text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE care_entries (
  id text PRIMARY KEY, patient_id text NOT NULL REFERENCES patients(id), clinic_id text NOT NULL,
  section entry_section NOT NULL, content text NOT NULL, author_id text NOT NULL,
  author_role user_role NOT NULL, entry_type text NOT NULL, provenance_pointer text,
  risk_level smallint NOT NULL DEFAULT 0 CHECK (risk_level BETWEEN 0 AND 3),
  tags text[] NOT NULL DEFAULT '{}', open_action boolean NOT NULL DEFAULT false,
  version integer NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE entry_versions (
  entry_id text NOT NULL REFERENCES care_entries(id), version integer NOT NULL, content text NOT NULL,
  changed_by text NOT NULL, change_reason text NOT NULL, changed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (entry_id, version)
);
CREATE TABLE comments (
  id text PRIMARY KEY, entry_id text NOT NULL REFERENCES care_entries(id), author_id text NOT NULL,
  author_role user_role NOT NULL, body text NOT NULL, mention_user_id text, assigned_to text,
  resolved boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE highlights (
  id text PRIMARY KEY, patient_id text NOT NULL REFERENCES patients(id), entry_id text NOT NULL REFERENCES care_entries(id),
  span_start integer NOT NULL DEFAULT 0, span_end integer NOT NULL DEFAULT 0,
  risk_reason text NOT NULL, provenance_pointer text NOT NULL UNIQUE, priority numeric NOT NULL,
  accepted boolean, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE audit_log (
  id bigserial PRIMARY KEY, entry_id text REFERENCES care_entries(id), actor_id text NOT NULL,
  action text NOT NULL, metadata jsonb NOT NULL DEFAULT '{}', occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE importance_feedback (
  clinic_id text NOT NULL, tag text NOT NULL, net_score integer NOT NULL DEFAULT 0,
  PRIMARY KEY(clinic_id, tag)
);

CREATE INDEX care_entries_patient_timeline_idx ON care_entries(patient_id, created_at DESC);
CREATE INDEX care_entries_glance_idx ON care_entries(patient_id, open_action, risk_level DESC, created_at DESC);

-- Request identity is set with SET LOCAL by PostgresStore; never expose tables via owner credentials.
ALTER TABLE patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE care_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE entry_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE highlights ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE importance_feedback ENABLE ROW LEVEL SECURITY;
-- The local application account may own these tables; force RLS so ownership
-- never becomes an accidental authorization bypass.
ALTER TABLE patients FORCE ROW LEVEL SECURITY;
ALTER TABLE care_entries FORCE ROW LEVEL SECURITY;
ALTER TABLE entry_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE comments FORCE ROW LEVEL SECURITY;
ALTER TABLE highlights FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;
ALTER TABLE importance_feedback FORCE ROW LEVEL SECURITY;

CREATE POLICY patient_scope ON patients USING (clinic_id = current_setting('app.clinic_id', true));
CREATE POLICY entry_read ON care_entries FOR SELECT USING (
 clinic_id = current_setting('app.clinic_id', true) AND
 (current_setting('app.role', true) <> 'patient' OR (section = 'patient_facing' AND author_role <> 'system'))
);
CREATE POLICY entry_insert ON care_entries FOR INSERT WITH CHECK (
 clinic_id = current_setting('app.clinic_id', true) AND
 ((current_setting('app.role', true) = 'staff' AND section = 'staff_notes' AND author_id = current_setting('app.user_id', true)) OR
  (current_setting('app.role', true) = 'clinician' AND section IN ('clinician_sections','patient_facing') AND author_id = current_setting('app.user_id', true)) OR
  current_setting('app.role', true) IN ('admin','system'))
);
CREATE POLICY entry_update ON care_entries FOR UPDATE USING (
 clinic_id = current_setting('app.clinic_id', true) AND
 ((current_setting('app.role', true) = 'staff' AND section = 'staff_notes' AND author_id = current_setting('app.user_id', true)) OR
  (current_setting('app.role', true) = 'clinician' AND section = 'clinician_sections' AND author_id = current_setting('app.user_id', true)) OR
  current_setting('app.role', true) = 'admin')
);
CREATE POLICY versions_read ON entry_versions FOR SELECT USING (EXISTS (SELECT 1 FROM care_entries e WHERE e.id = entry_id));
CREATE POLICY versions_write ON entry_versions FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM care_entries e WHERE e.id = entry_id));
CREATE POLICY comments_policy ON comments USING (EXISTS (SELECT 1 FROM care_entries e WHERE e.id = entry_id) AND current_setting('app.role', true) <> 'patient') WITH CHECK (current_setting('app.role', true) <> 'patient');
CREATE POLICY highlights_policy ON highlights USING (EXISTS (SELECT 1 FROM care_entries e WHERE e.id = entry_id)) WITH CHECK (EXISTS (SELECT 1 FROM care_entries e WHERE e.id = entry_id));
CREATE POLICY audit_read ON audit_log FOR SELECT USING (EXISTS (SELECT 1 FROM care_entries e WHERE e.id = entry_id));
CREATE POLICY audit_write ON audit_log FOR INSERT WITH CHECK (true);
CREATE POLICY feedback_scope ON importance_feedback USING (clinic_id = current_setting('app.clinic_id', true)) WITH CHECK (clinic_id = current_setting('app.clinic_id', true));
