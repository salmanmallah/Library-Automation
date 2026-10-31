import unittest
from datetime import timedelta
from core.auth.security import hash_password, verify_password, create_access_token, decode_access_token
from core.database.session import SessionLocal, init_db
from core.database.models.user import User

class TestAuthSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_argon2_password_hashing(self):
        plain = "SecureInstitutionalPass#2026"
        hashed = hash_password(plain)
        self.assertNotEqual(plain, hashed)
        self.assertTrue(hashed.startswith("$argon2id$"))

        # Verify correct password
        self.assertTrue(verify_password(plain, hashed))
        # Verify wrong password
        self.assertFalse(verify_password("WrongPassword123", hashed))

    def test_jwt_token_generation_and_decode(self):
        payload = {"sub": "42", "role": "librarian", "name": "Jane Doe"}
        token = create_access_token(payload, expires_delta=timedelta(minutes=30))
        self.assertIsInstance(token, str)

        decoded = decode_access_token(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.get("sub"), "42")
        self.assertEqual(decoded.get("role"), "librarian")
        self.assertEqual(decoded.get("name"), "Jane Doe")

    def test_jwt_tampered_token_fails(self):
        payload = {"sub": "99", "role": "member"}
        token = create_access_token(payload)
        tampered_token = token[:-5] + "XXXXX"
        decoded = decode_access_token(tampered_token)
        self.assertIsNone(decoded)

if __name__ == "__main__":
    unittest.main()
