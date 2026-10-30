import os
import unittest
import tempfile
from core.config import AppConfig
from core.storage import StorageManager
from core.book_service import BookRecord

class TestStorageManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = os.path.join(self.temp_dir.name, "test_books.csv")
        self.db_path = os.path.join(self.temp_dir.name, "test_books.db")

        self.sample_book = BookRecord(
            isbn="9780132350884",
            title="Clean Code",
            authors="Robert C. Martin",
            publisher="Prentice Hall",
            publish_date="2008-08-01",
            page_count=464,
            categories="Computers",
            description="A Handbook of Agile Software Craftsmanship",
            scanned_at="2026-10-30 12:00:00"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_csv_storage_and_deduplication(self):
        config = AppConfig(csv_file_path=self.csv_path, use_sqlite=False)
        storage = StorageManager(config)

        # Initial check
        self.assertFalse(storage.is_registered("9780132350884"))

        # Save book
        saved = storage.save_book(self.sample_book)
        self.assertTrue(saved)
        self.assertTrue(storage.is_registered("9780132350884"))

        # Attempt duplicate save
        saved_duplicate = storage.save_book(self.sample_book)
        self.assertFalse(saved_duplicate)

        # Re-initialize storage from disk and verify persistence
        new_storage = StorageManager(config)
        self.assertTrue(new_storage.is_registered("9780132350884"))

    def test_sqlite_storage_and_deduplication(self):
        config = AppConfig(db_file_path=self.db_path, use_sqlite=True)
        storage = StorageManager(config)

        self.assertFalse(storage.is_registered("9780132350884"))

        saved = storage.save_book(self.sample_book)
        self.assertTrue(saved)
        self.assertTrue(storage.is_registered("9780132350884"))

        # Re-initialize and check
        new_storage = StorageManager(config)
        self.assertTrue(new_storage.is_registered("9780132350884"))

if __name__ == "__main__":
    unittest.main()
