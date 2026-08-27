-- Admin-only patient-page deletion with referentially complete cleanup.
ALTER TABLE care_entries DROP CONSTRAINT care_entries_patient_id_fkey;
ALTER TABLE care_entries ADD CONSTRAINT care_entries_patient_id_fkey
  FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE;

ALTER TABLE entry_versions DROP CONSTRAINT entry_versions_entry_id_fkey;
ALTER TABLE entry_versions ADD CONSTRAINT entry_versions_entry_id_fkey
  FOREIGN KEY (entry_id) REFERENCES care_entries(id) ON DELETE CASCADE;

ALTER TABLE comments DROP CONSTRAINT comments_entry_id_fkey;
ALTER TABLE comments ADD CONSTRAINT comments_entry_id_fkey
  FOREIGN KEY (entry_id) REFERENCES care_entries(id) ON DELETE CASCADE;

ALTER TABLE highlights DROP CONSTRAINT highlights_patient_id_fkey;
ALTER TABLE highlights ADD CONSTRAINT highlights_patient_id_fkey
  FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE;
ALTER TABLE highlights DROP CONSTRAINT highlights_entry_id_fkey;
ALTER TABLE highlights ADD CONSTRAINT highlights_entry_id_fkey
  FOREIGN KEY (entry_id) REFERENCES care_entries(id) ON DELETE CASCADE;
ALTER TABLE highlights DROP CONSTRAINT highlights_reason_entry_id_fkey;
ALTER TABLE highlights ADD CONSTRAINT highlights_reason_entry_id_fkey
  FOREIGN KEY (reason_entry_id) REFERENCES care_entries(id) ON DELETE SET NULL;

ALTER TABLE audit_log DROP CONSTRAINT audit_log_entry_id_fkey;
ALTER TABLE audit_log ADD CONSTRAINT audit_log_entry_id_fkey
  FOREIGN KEY (entry_id) REFERENCES care_entries(id) ON DELETE CASCADE;

DROP POLICY IF EXISTS patients_delete ON patients;
CREATE POLICY patients_delete ON patients FOR DELETE USING (
  clinic_id = current_setting('app.clinic_id', true)
  AND current_setting('app.role', true) = 'admin'
);

GRANT DELETE ON patients TO nightingale_app;
