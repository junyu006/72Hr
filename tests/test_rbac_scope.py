import unittest

from nightingale.service import PermissionDenied
from tests.helpers import setup_service


class RbacScopeTests(unittest.TestCase):
    def test_roles_cannot_write_each_others_sections(self):
        service, a = setup_service()
        staff_note = service.create_entry(a["staff"], patient_id="p1", section="staff_notes", content="call patient", entry_type="staff_manual_log")
        clinician_note = service.create_entry(a["clinician"], patient_id="p1", section="clinician_sections", content="plan", entry_type="clinician_manual_log")
        with self.assertRaises(PermissionDenied): service.edit(a["clinician"], staff_note.id, "changed")
        with self.assertRaises(PermissionDenied): service.edit(a["staff"], clinician_note.id, "changed")
        with self.assertRaises(PermissionDenied): service.timeline(a["other_staff"], "p1")

    def test_patient_cannot_see_internal_or_raw_ai(self):
        service, a = setup_service()
        service.create_entry(a["staff"], patient_id="p1", section="staff_notes", content="internal", entry_type="staff_manual_log")
        ai = service.ingest_ai_scribe(a["system"], patient_id="p1", content="raw scribe", ai_type="ai_patient_session_summary", session_id="s1")
        service.create_entry(a["clinician"], patient_id="p1", section="patient_facing", content="take rest", entry_type="patient_facing_log")
        self.assertEqual([e.content for e in service.timeline(a["patient"], "p1")], ["take rest"])
        with self.assertRaises(PermissionDenied): service.add_comment(a["patient"], ai.id, "nope")
