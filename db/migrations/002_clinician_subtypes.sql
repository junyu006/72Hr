-- Set app.clinician_kind transaction-locally to doctor or nurse.
DROP POLICY entry_insert ON care_entries;
CREATE POLICY entry_insert ON care_entries FOR INSERT WITH CHECK (
 clinic_id = current_setting('app.clinic_id', true) AND
 ((current_setting('app.role', true) = 'staff' AND section = 'staff_notes' AND author_id = current_setting('app.user_id', true)) OR
  (current_setting('app.role', true) = 'clinician' AND section = 'clinician_sections' AND author_id = current_setting('app.user_id', true) AND
   ((current_setting('app.clinician_kind', true) = 'doctor' AND entry_type IN ('doctor_daily','doctor_patient_consult','doctor_other')) OR
    (current_setting('app.clinician_kind', true) = 'nurse' AND entry_type IN ('nurse_daily','nurse_patient_consult','nurse_other')))) OR
  (current_setting('app.role', true) = 'clinician' AND section = 'patient_facing' AND author_id = current_setting('app.user_id', true)) OR
  current_setting('app.role', true) IN ('admin','system'))
);
