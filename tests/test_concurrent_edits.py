import unittest
from concurrent.futures import ThreadPoolExecutor

from nightingale.service import PermissionDenied
from tests.helpers import setup_service


class ConcurrentEditTests(unittest.TestCase):
    def test_different_sections_do_not_overwrite_each_other(self):
        service, a = setup_service()
        staff = service.create_entry(a["staff"], patient_id="p1", section="staff_notes", content="call", entry_type="staff_manual_log")
        plan = service.create_entry(a["clinician"], patient_id="p1", section="clinician_sections", content="plan", entry_type="clinician_manual_log")
        with ThreadPoolExecutor(max_workers=2) as executor:
            staff_edit = executor.submit(service.edit, a["staff"], staff.id, "called", 1)
            clinician_edit = executor.submit(service.edit, a["clinician"], plan.id, "updated plan", 1)
            self.assertEqual(staff_edit.result().version, 2)
            self.assertEqual(clinician_edit.result().version, 2)
        self.assertEqual(service.entries[staff.id].content, "called")
        self.assertEqual(service.entries[plan.id].content, "updated plan")

    def test_same_section_uses_optimistic_version_conflict(self):
        service, a = setup_service()
        entry = service.create_entry(a["clinician"], patient_id="p1", section="clinician_sections", content="v1", entry_type="clinician_manual_log")
        service.edit(a["clinician"], entry.id, "v2", 1)
        with self.assertRaisesRegex(PermissionDenied, "stale version"):
            service.edit(a["clinician"], entry.id, "stale v2", 1)
        self.assertEqual(service.entries[entry.id].content, "v2")
        self.assertEqual(service.entries[entry.id].version, 2)
