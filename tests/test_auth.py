import unittest

from nightingale.auth import hash_password, new_session_token, token_digest, verify_password


class AuthenticationTests(unittest.TestCase):
    def test_passwords_are_salted_hashed_and_verified(self):
        first = hash_password("Doctor123!")
        second = hash_password("Doctor123!")
        self.assertNotEqual(first, second)
        self.assertNotIn("Doctor123!", first)
        self.assertTrue(verify_password("Doctor123!", first))
        self.assertFalse(verify_password("wrong-password", first))

    def test_session_tokens_are_opaque_and_stored_as_digests(self):
        token = new_session_token()
        self.assertGreaterEqual(len(token), 40)
        self.assertNotEqual(token, token_digest(token))


if __name__ == "__main__":
    unittest.main()
