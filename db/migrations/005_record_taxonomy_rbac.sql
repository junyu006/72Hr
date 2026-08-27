-- Canonical eight-type record taxonomy and database-enforced RBAC.
-- Existing content and version history are retained; legacy type names are normalized.
UPDATE care_entries SET entry_type = CASE
  WHEN section = 'patient_facing' THEN 'patient_facing_log'
  WHEN section = 'staff_notes' THEN 'staff_manual_log'
  WHEN section = 'clinician_sections' AND entry_type = 'doctor_patient_consult' THEN 'doctor_patient_consult'
  WHEN section = 'clinician_sections' AND entry_type = 'nurse_patient_consult' THEN 'nurse_patient_consult'
  WHEN section = 'clinician_sections' THEN 'clinician_manual_log'
  WHEN section = 'ai_scribed' AND entry_type = 'ai_patient_consult' THEN 'ai_patient_consult'
  WHEN section = 'ai_scribed' AND entry_type = 'system_generated_event' THEN 'system_generated_event'
  WHEN section = 'ai_scribed' THEN 'ai_scribe_log'
  ELSE entry_type
END;

DROP POLICY IF EXISTS entry_read ON care_entries;
DROP POLICY IF EXISTS entry_insert ON care_entries;
DROP POLICY IF EXISTS entry_update ON care_entries;

CREATE POLICY entry_read ON care_entries FOR SELECT USING (
  clinic_id = current_setting('app.clinic_id', true) AND
  (current_setting('app.role', true) IN ('clinician','admin','system') OR
   (current_setting('app.role', true) = 'staff' AND entry_type = 'staff_manual_log') OR
   (current_setting('app.role', true) = 'patient' AND entry_type = 'patient_facing_log' AND EXISTS (
      SELECT 1 FROM patient_accounts pa
      WHERE pa.patient_id = care_entries.patient_id
        AND pa.patient_user_id = current_setting('app.user_id', true)
        AND pa.clinic_id = current_setting('app.clinic_id', true))))
);

CREATE POLICY entry_insert ON care_entries FOR INSERT WITH CHECK (
  clinic_id = current_setting('app.clinic_id', true)
  AND author_id = current_setting('app.user_id', true)
  AND ((entry_type IN ('system_generated_event','ai_scribe_log','ai_patient_consult') AND section = 'ai_scribed')
    OR (entry_type IN ('doctor_patient_consult','nurse_patient_consult','clinician_manual_log') AND section = 'clinician_sections')
    OR (entry_type = 'staff_manual_log' AND section = 'staff_notes')
    OR (entry_type = 'patient_facing_log' AND section = 'patient_facing'))
  AND (
    (current_setting('app.role', true) = 'staff' AND entry_type = 'staff_manual_log')
    OR (current_setting('app.role', true) = 'clinician' AND
       ((current_setting('app.clinician_kind', true) = 'doctor' AND entry_type IN ('doctor_patient_consult','clinician_manual_log','patient_facing_log'))
        OR (current_setting('app.clinician_kind', true) = 'nurse' AND entry_type IN ('nurse_patient_consult','clinician_manual_log','patient_facing_log'))))
    OR (current_setting('app.role', true) = 'system' AND entry_type IN ('system_generated_event','ai_scribe_log','ai_patient_consult'))
    OR current_setting('app.role', true) = 'admin')
);

CREATE POLICY entry_update ON care_entries FOR UPDATE USING (
  clinic_id = current_setting('app.clinic_id', true) AND (
    (current_setting('app.role', true) = 'staff' AND entry_type = 'staff_manual_log')
    OR (current_setting('app.role', true) = 'clinician' AND
       ((current_setting('app.clinician_kind', true) = 'doctor' AND entry_type IN ('doctor_patient_consult','clinician_manual_log','patient_facing_log'))
        OR (current_setting('app.clinician_kind', true) = 'nurse' AND entry_type IN ('nurse_patient_consult','clinician_manual_log','patient_facing_log'))))
    OR current_setting('app.role', true) = 'admin')
) WITH CHECK (
  clinic_id = current_setting('app.clinic_id', true) AND (
    (current_setting('app.role', true) = 'staff' AND entry_type = 'staff_manual_log')
    OR (current_setting('app.role', true) = 'clinician' AND
       ((current_setting('app.clinician_kind', true) = 'doctor' AND entry_type IN ('doctor_patient_consult','clinician_manual_log','patient_facing_log'))
        OR (current_setting('app.clinician_kind', true) = 'nurse' AND entry_type IN ('nurse_patient_consult','clinician_manual_log','patient_facing_log'))))
    OR current_setting('app.role', true) = 'admin')
);

DROP POLICY IF EXISTS versions_write ON entry_versions;
CREATE POLICY versions_write ON entry_versions FOR INSERT WITH CHECK (
  current_setting('app.role', true) <> 'patient'
  AND EXISTS (SELECT 1 FROM care_entries e WHERE e.id = entry_id)
);

DROP POLICY IF EXISTS highlights_policy ON highlights;
CREATE POLICY highlights_read ON highlights FOR SELECT USING (
  EXISTS (SELECT 1 FROM care_entries e WHERE e.id = entry_id)
);
CREATE POLICY highlights_insert ON highlights FOR INSERT WITH CHECK (
  current_setting('app.role', true) IN ('clinician','admin','system')
  AND EXISTS (
    SELECT 1 FROM care_entries e
    WHERE e.id = entry_id AND e.entry_type IN ('ai_scribe_log','ai_patient_consult'))
);
