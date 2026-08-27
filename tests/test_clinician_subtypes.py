import unittest

from nightingale.clinical import ai_summary_type, attach_consult_source, authorised_summary_sources, validate_clinical_entry
from nightingale.domain import Actor, ClinicianKind, Role


class ClinicianSubtypeTests(unittest.TestCase):
    def test_cross_consult_types_are_rejected(self):
        doctor = Actor("doctor_1", Role.CLINICIAN, "clinic_a", ClinicianKind.DOCTOR)
        nurse = Actor("nurse_1", Role.CLINICIAN, "clinic_a", ClinicianKind.NURSE)
        with self.assertRaises(PermissionError): validate_clinical_entry(doctor, "nurse_patient_consult")
        with self.assertRaises(PermissionError): validate_clinical_entry(nurse, "doctor_patient_consult")

    def test_consults_map_to_ai_summary_types(self):
        self.assertEqual(ai_summary_type("doctor_patient_consult"), "ai_scribe_log")
        self.assertEqual(ai_summary_type("nurse_patient_consult"), "ai_scribe_log")

    def test_only_visible_model_references_become_source_buttons(self):
        visible = [{"id": "entry_abc123", "content": "patient-facing instruction"}]
        summary = "Follow-up | laboratory review needed | entry_abc123; internal note | entry_deadbeef"
        self.assertEqual(authorised_summary_sources(summary, visible), [{"entry_id": "entry_abc123", "label": "patient-facing instruction"}])

    def test_consult_source_is_attached_after_model_generation(self):
        self.assertEqual(
            attach_consult_source("Brief consult summary. ", "entry_abc123"),
            "Brief consult summary.\n\nSource consult: entry_abc123",
        )
