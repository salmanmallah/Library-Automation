import unittest
from core.database.session import SessionLocal, init_db
from core.database.models.catalog import Book, Category
from core.database.models.inventory import BookCopy, Shelf
from core.services import catalog_service, inventory_service

class TestCatalogService(unittest.TestCase):
    def setUp(self):
        init_db()
        self.db = SessionLocal()
        # Clean up test ISBNs before test
        for isbn in ["9780134494166", "9780321125217"]:
            b = self.db.query(Book).filter(Book.isbn == isbn).first()
            if b:
                self.db.delete(b)
        self.db.commit()

    def tearDown(self):
        # Clean up test ISBNs after test
        for isbn in ["9780134494166", "9780321125217"]:
            b = self.db.query(Book).filter(Book.isbn == isbn).first()
            if b:
                self.db.delete(b)
        self.db.commit()
        self.db.close()

    def test_create_book_with_auto_copies(self):
        book_data = {
            "isbn": "9780134494166",
            "title": "Clean Architecture: A Craftsman's Guide to Software Structure",
            "authors": "Robert C. Martin",
            "publisher": "Prentice Hall",
            "publish_date": "2017",
            "page_count": 432,
            "categories": "Software Engineering",
            "description": "Rules of architecture apply to all software."
        }
        book, is_created = catalog_service.create_or_update_book(
            self.db,
            book_data,
            initial_copies=3
        )
        self.assertTrue(is_created)
        self.assertEqual(book.isbn, "9780134494166")
        self.assertEqual(len(book.copies), 3)
        self.assertEqual(book.copies[0].status, "available")
        self.assertTrue(book.copies[0].copy_barcode.startswith("BC-9780134494166-"))

    def test_search_books(self):
        # Ensure a book with Clean exists
        catalog_service.create_or_update_book(
            self.db,
            {"isbn": "9780134494166", "title": "Clean Architecture"},
            initial_copies=1
        )
        books, total = catalog_service.get_books(self.db, query="Clean", page=1, page_size=10)
        self.assertGreaterEqual(total, 1)
        self.assertTrue(any("Clean" in b["title"] for b in books))

    def test_delete_book_cleanly(self):
        book_data = {
            "isbn": "9780321125217",
            "title": "Domain-Driven Design",
            "authors": "Eric Evans",
            "publisher": "Addison-Wesley",
            "publish_date": "2003"
        }
        book, _ = catalog_service.create_or_update_book(self.db, book_data, initial_copies=1)
        book_id = book.id

        success = catalog_service.delete_book(self.db, book_id)
        self.assertTrue(success)
        self.assertIsNone(catalog_service.get_book_by_id(self.db, book_id))

if __name__ == "__main__":
    unittest.main()
