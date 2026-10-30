import unittest
from core.isbn_utils import (
    clean_isbn_string,
    is_valid_isbn10,
    is_valid_isbn13,
    validate_and_normalize_isbn
)

class TestISBNUtils(unittest.TestCase):
    def test_clean_isbn_string(self):
        # Raw bytes
        self.assertEqual(clean_isbn_string(b"978-0-13-235088-4"), "9780132350884")
        # String with spaces and dashes
        self.assertEqual(clean_isbn_string(" 978-0 13 235088-4 "), "9780132350884")
        # URI format
        self.assertEqual(clean_isbn_string("urn:isbn:9780132350884"), "9780132350884")

    def test_valid_isbn13(self):
        valid_13 = "9780132350884"  # Clean Code
        self.assertTrue(is_valid_isbn13(valid_13))
        # Valid 979 prefix
        self.assertTrue(is_valid_isbn13("9798218482442"))
        # Corrupt last digit
        self.assertFalse(is_valid_isbn13("9780132350885"))
        # Invalid Bookland prefix (e.g. 918, 007, 618)
        self.assertFalse(is_valid_isbn13("9187416511656"))
        self.assertFalse(is_valid_isbn13("0074100009447"))

    def test_valid_isbn10(self):
        valid_10 = "0132350882"
        self.assertTrue(is_valid_isbn10(valid_10))
        # Valid with X check digit
        valid_10_x = "080442957X"
        self.assertTrue(is_valid_isbn10(valid_10_x))
        # Corrupt check digit
        self.assertFalse(is_valid_isbn10("0804429579"))

    def test_validate_and_normalize_isbn(self):
        self.assertEqual(validate_and_normalize_isbn(b"978-0-13-235088-4"), "9780132350884")
        self.assertEqual(validate_and_normalize_isbn("0-13-235088-2"), "0132350882")
        self.assertIsNone(validate_and_normalize_isbn("12345"))  # Too short
        self.assertIsNone(validate_and_normalize_isbn("ABCDEFGHIJ"))  # Not numbers
        # Non-book barcodes rejected
        self.assertIsNone(validate_and_normalize_isbn("9187416511656"))
        self.assertIsNone(validate_and_normalize_isbn("0074100009447"))

if __name__ == "__main__":
    unittest.main()
