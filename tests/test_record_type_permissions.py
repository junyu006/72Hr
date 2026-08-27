import unittest

from nightingale.service import PermissionDenied
from tests.helpers import setup_service


class RecordTypePermissionTests(unittest.TestCase):
    def test_patient_cannot_create_any_record(self):
        service, actors = setup_service()
        with self.assertRaises(PermissionDenied):
            service.create_entry(actors["patient"], patient_id="p1", section="patient_facing", content="write", entry_type="patient_facing_log")

    def test_doctor_and_nurse_have_distinct_consult_write_permissions(self):
        service, actors = setup_service()
        doctor_consult = service.create_entry(actors["clinician"], patient_id="p1", section="clinician_sections", content="doctor", entry_type="doctor_patient_consult")
        nurse_consult = service.create_entry(actors["nurse"], patient_id="p1", section="clinician_sections", content="nurse", entry_type="nurse_patient_consult")
        with self.assertRaises(PermissionDenied):
            service.create_entry(actors["clinician"], patient_id="p1", section="clinician_sections", content="wrong", entry_type="nurse_patient_consult")
        with self.assertRaises(PermissionDenied):
            service.create_entry(actors["nurse"], patient_id="p1", section="clinician_sections", content="wrong", entry_type="doctor_patient_consult")
        self.assertEqual({entry.id for entry in service.timeline(actors["clinician"], "p1")}, {doctor_consult.id, nurse_consult.id})
        self.assertEqual({entry.id for entry in service.timeline(actors["nurse"], "p1")}, {doctor_consult.id, nurse_consult.id})

    def test_staff_is_limited_to_staff_manual_logs(self):
        service, actors = setup_service()
        staff_log = service.create_entry(actors["staff"], patient_id="p1", section="staff_notes", content="call", entry_type="staff_manual_log")
        service.edit(actors["staff"], staff_log.id, "called", 1)
        with self.assertRaises(PermissionDenied):
            service.create_entry(actors["staff"], patient_id="p1", section="patient_facing", content="wrong", entry_type="patient_facing_log")

    def test_clinician_cannot_edit_ai_but_can_highlight_it(self):
        service, actors = setup_service()
        ai_log = service.ingest_ai_scribe(actors["system"], patient_id="p1", content="review medication", ai_type="ai_scribe_log", session_id="s1")
        with self.assertRaises(PermissionDenied):
            service.edit(actors["clinician"], ai_log.id, "changed", 1)
        highlight = service.highlight(actors["clinician"], ai_log.id, "Medication requires review", 80, (7, 17))
        self.assertEqual(highlight.entry_id, ai_log.id)

    def test_clinician_can_highlight_non_ai_records(self):
        service, actors = setup_service()
        consult = service.create_entry(actors["clinician"], patient_id="p1", section="clinician_sections", content="review hydration", entry_type="doctor_patient_consult")
        staff_log = service.create_entry(actors["staff"], patient_id="p1", section="staff_notes", content="follow-up call", entry_type="staff_manual_log")
        self.assertEqual(service.highlight(actors["clinician"], consult.id, "Consult keyword", 70, (0, 6)).entry_id, consult.id)
        self.assertEqual(service.highlight(actors["clinician"], staff_log.id, "Staff keyword", 70, (0, 9)).entry_id, staff_log.id)
        with self.assertRaises(PermissionDenied):
            service.highlight(actors["staff"], staff_log.id, "Not allowed", 70, (0, 9))
        with self.assertRaises(PermissionDenied):
            service.highlight(actors["patient"], consult.id, "Not allowed", 70, (0, 6))

    def test_only_clinician_or_admin_can_delete_a_visible_highlight(self):
        service, actors = setup_service()
        entry = service.create_entry(actors["clinician"], patient_id="p1", section="clinician_sections", content="review hydration", entry_type="doctor_patient_consult")
        highlight = service.highlight(actors["clinician"], entry.id, "Review", 70, (0, 6))
        with self.assertRaises(PermissionDenied):
            service.delete_highlight(actors["patient"], highlight.id)
        self.assertEqual(service.delete_highlight(actors["admin"], highlight.id).id, highlight.id)
        self.assertNotIn(highlight.id, service.highlights)

    def test_admin_can_create_and_edit_every_record_type(self):
        service, actors = setup_service()
        combinations = {
            "system_generated_event":"ai_scribed", "ai_scribe_log":"ai_scribed",
            "doctor_patient_consult":"clinician_sections", "nurse_patient_consult":"clinician_sections",
            "ai_patient_consult":"ai_scribed", "staff_manual_log":"staff_notes",
            "clinician_manual_log":"clinician_sections", "patient_facing_log":"patient_facing",
        }
        for entry_type, section in combinations.items():
            entry = service.create_entry(actors["admin"], patient_id="p1", section=section, content=entry_type, entry_type=entry_type)
            self.assertEqual(service.edit(actors["admin"], entry.id, f"edited {entry_type}", 1).version, 2)


if __name__ == "__main__":
    unittest.main()
