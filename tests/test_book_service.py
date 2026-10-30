import unittest
from unittest.mock import patch, MagicMock
from core.config import AppConfig
from core.book_service import BookService

class TestBookService(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig()
        self.service = BookService(self.config)

    @patch("requests.Session.get")
    def test_fetch_by_isbn_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "totalItems": 1,
            "items": [
                {
                    "volumeInfo": {
                        "title": "Design Patterns",
                        "authors": ["Erich Gamma", "Richard Helm", "Ralph Johnson", "John Vlissides"],
                        "publisher": "Addison-Wesley",
                        "publishedDate": "1994",
                        "pageCount": 395,
                        "categories": ["Computers / Programming"],
                        "description": "Capturing a wealth of experience about the design of object-oriented software."
                    }
                }
            ]
        }
        mock_get.return_value = mock_response

        record = self.service.fetch_by_isbn("9780201633610")
        self.assertIsNotNone(record)
        self.assertEqual(record.title, "Design Patterns")
        self.assertIn("Erich Gamma", record.authors)
        self.assertIn("John Vlissides", record.authors)
        self.assertEqual(record.page_count, 395)

    @patch("requests.Session.get")
    def test_fetch_by_isbn_not_found(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"totalItems": 0}
        mock_get.return_value = mock_response

        record = self.service.fetch_by_isbn("0000000000")
        self.assertIsNone(record)

if __name__ == "__main__":
    unittest.main()
