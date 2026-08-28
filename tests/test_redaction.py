import unittest

from nightingale.redaction import (
    PHIRedactionUnavailable,
    phileas_policy_definition,
    redact_for_llm,
    redact_glance_timeline,
)


class PHIRedactionTests(unittest.TestCase):
    def test_phileas_redacts_builtin_and_singapore_phi(self):
        text = (
            "Dr Ava Morgan, NRIC S1234567D, can be reached at +65 8123 4567 or "
            "ava.morgan@example.com on 12/03/2026."
        )
        redacted = redact_for_llm(text)

        for phi in ("Dr Ava Morgan", "S1234567D", "+65 8123 4567", "ava.morgan@example.com", "12/03/2026"):
            self.assertNotIn(phi, redacted)
        self.assertIn("[REDACTED-honorific-name]", redacted)
        self.assertIn("[REDACTED-singapore-nric-fin]", redacted)
        self.assertIn("[REDACTED-singapore-phone-number]", redacted)
        self.assertIn("[REDACTED-email-address]", redacted)

    def test_policy_includes_phileas_and_local_identifier_rules(self):
        identifiers = phileas_policy_definition()["identifiers"]
        self.assertIn("emailAddress", identifiers)
        classifications = {
            item["classification"] for item in identifiers["identifiers"]
        }
        self.assertEqual(
            classifications,
            {"singapore-nric-fin", "singapore-phone-number", "honorific-name"},
        )

    def test_glance_redacts_content_but_preserves_source_entry_id(self):
        source = redact_glance_timeline(
            [{
                "id": "entry_a11ce001",
                "created_at": "2026-08-28 10:30:00+00:00",
                "content": "Dr Ava Morgan can be reached at ava.morgan@example.com.",
            }]
        )

        self.assertIn("Source Entry ID: entry_a11ce001", source)
        self.assertNotIn("Dr Ava Morgan", source)
        self.assertNotIn("ava.morgan@example.com", source)

    def test_glance_rejects_untrusted_entry_id(self):
        with self.assertRaises(PHIRedactionUnavailable):
            redact_glance_timeline(
                [{"id": "ignore instructions", "created_at": "", "content": "note"}]
            )
