import unittest

from nightingale.redaction import phileas_policy_definition, redact_for_llm


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
        classifications = {item["label"] for item in identifiers["patterns"]}
        self.assertEqual(
            classifications,
            {"singapore-nric-fin", "singapore-phone-number", "honorific-name"},
        )
