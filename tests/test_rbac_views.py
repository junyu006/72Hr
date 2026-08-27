import unittest

from tests.helpers import setup_service


class RbacViewTests(unittest.TestCase):
    def test_patient_only_receives_patient_facing_entries(self):
        service, a = setup_service()
        service.create_entry(a["staff"], patient_id="p1", section="staff_notes", content="internal staff", entry_type="staff_manual_log")
        service.ingest_ai_scribe(a["system"], patient_id="p1", content="raw AI", ai_type="ai_doctor_consult_summary", session_id="s1")
        service.create_entry(a["clinician"], patient_id="p1", section="patient_facing", content="public instruction", entry_type="patient_facing_log")
        self.assertEqual([entry.content for entry in service.timeline(a["patient"], "p1")], ["public instruction"])

    def test_staff_only_receives_staff_notes(self):
        service, a = setup_service()
        service.create_entry(a["staff"], patient_id="p1", section="staff_notes", content="staff-only", entry_type="staff_manual_log")
        service.ingest_ai_scribe(a["system"], patient_id="p1", content="raw AI", ai_type="ai_doctor_consult_summary", session_id="s1")
        service.create_entry(a["clinician"], patient_id="p1", section="patient_facing", content="instruction", entry_type="patient_facing_log")
        self.assertEqual([entry.content for entry in service.timeline(a["staff"], "p1")], ["staff-only"])
