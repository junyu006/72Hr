-- Patient identity is explicitly bound to one patient record. In production
-- patient_user_id comes from verified authentication claims, never a UI field.
CREATE TABLE patient_accounts (
  patient_id text PRIMARY KEY REFERENCES patients(id) ON DELETE CASCADE,
  patient_user_id text NOT NULL UNIQUE,
  clinic_id text NOT NULL
);

ALTER TABLE patient_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE patient_accounts FORCE ROW LEVEL SECURITY;

DROP POLICY patient_scope ON patients;
CREATE POLICY patients_read ON patients FOR SELECT USING (
  clinic_id = current_setting('app.clinic_id', true) AND
  (current_setting('app.role', true) IN ('staff','clinician','admin','system') OR
   (current_setting('app.role', true) = 'patient' AND EXISTS (
      SELECT 1 FROM patient_accounts pa
      WHERE pa.patient_id = patients.id
        AND pa.patient_user_id = current_setting('app.user_id', true)
        AND pa.clinic_id = current_setting('app.clinic_id', true))))
);
CREATE POLICY patients_write ON patients FOR INSERT WITH CHECK (
  clinic_id = current_setting('app.clinic_id', true)
  AND current_setting('app.role', true) IN ('staff','clinician','admin')
);

CREATE POLICY patient_account_self ON patient_accounts FOR SELECT USING (
  clinic_id = current_setting('app.clinic_id', true) AND
  patient_user_id = current_setting('app.user_id', true)
);
CREATE POLICY patient_account_admin ON patient_accounts FOR ALL USING (
  clinic_id = current_setting('app.clinic_id', true) AND current_setting('app.role', true) = 'admin'
) WITH CHECK (
  clinic_id = current_setting('app.clinic_id', true) AND current_setting('app.role', true) = 'admin'
);

DROP POLICY entry_read ON care_entries;
CREATE POLICY entry_read ON care_entries FOR SELECT USING (
  clinic_id = current_setting('app.clinic_id', true) AND
  (current_setting('app.role', true) IN ('admin','system') OR
   (current_setting('app.role', true) = 'clinician' AND section IN ('clinician_sections','staff_notes','ai_scribed','patient_facing')) OR
   (current_setting('app.role', true) = 'staff' AND section = 'staff_notes') OR
   (current_setting('app.role', true) = 'patient' AND section = 'patient_facing' AND EXISTS (
      SELECT 1 FROM patient_accounts pa
      WHERE pa.patient_id = care_entries.patient_id
        AND pa.patient_user_id = current_setting('app.user_id', true)
        AND pa.clinic_id = current_setting('app.clinic_id', true))))
);
