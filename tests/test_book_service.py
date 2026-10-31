import unittest
from unittest.mock import patch, MagicMock
from core.config import AppConfig
from core.book_service import BookService

class TestBookService(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig()
        self.service = BookService(self.config)

    @patch("requests.Session.get")
    def test_fetch_by_isbn_openlibrary_success(self, mock_get):
        # OpenLibrary returns a dictionary keyed by ISBN:clean_isbn
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ISBN:9780132350884": {
                "title": "Clean Code",
                "authors": [{"name": "Robert C. Martin"}],
                "publishers": [{"name": "Prentice Hall"}],
                "publish_date": "2008",
                "number_of_pages": 464,
                "subjects": [{"name": "Software Engineering"}],
                "cover": {"medium": "https://covers.openlibrary.org/b/id/15126503-M.jpg"}
            }
        }
        mock_get.return_value = mock_response

        record = self.service.fetch_by_isbn("9780132350884")
        self.assertIsNotNone(record)
        self.assertEqual(record.title, "Clean Code")
        self.assertEqual(record.authors, "Robert C. Martin")
        self.assertEqual(record.publisher, "Prentice Hall")
        self.assertEqual(record.page_count, 464)
        self.assertEqual(record.cover_image_url, "https://covers.openlibrary.org/b/id/15126503-M.jpg")

    @patch("requests.Session.get")
    def test_fetch_by_isbn_google_books_fallback(self, mock_get):
        # First call (OpenLibrary) returns empty, second call (Google Books) returns item
        ol_res = MagicMock()
        ol_res.status_code = 200
        ol_res.json.return_value = {}

        gb_res = MagicMock()
        gb_res.status_code = 200
        gb_res.json.return_value = {
            "totalItems": 1,
            "items": [
                {
                    "volumeInfo": {
                        "title": "Design Patterns",
                        "authors": ["Erich Gamma", "Richard Helm"],
                        "publisher": "Addison-Wesley",
                        "publishedDate": "1994",
                        "pageCount": 395,
                        "categories": ["Computers / Programming"],
                        "description": "Object-oriented design patterns."
                    }
                }
            ]
        }
        mock_get.side_effect = [ol_res, gb_res]

        record = self.service.fetch_by_isbn("9780201633610")
        self.assertIsNotNone(record)
        self.assertEqual(record.title, "Design Patterns")
        self.assertIn("Erich Gamma", record.authors)
        self.assertEqual(record.page_count, 395)

    @patch("requests.Session.get")
    def test_fetch_by_isbn_not_found(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response

        record = self.service.fetch_by_isbn("0000000000")
        self.assertIsNone(record)

if __name__ == "__main__":
    unittest.main()
